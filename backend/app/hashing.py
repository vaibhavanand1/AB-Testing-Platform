import hashlib
from typing import Any, Dict, List, Tuple
import redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Assignment, Experiment


def compute_variant(experiment_id: int, user_id: str, variants: List[Dict[str, Any]]) -> str:
    total_weight = sum(v["weight"] for v in variants)
    if total_weight <= 0:
        raise ValueError("Total variant weight must be greater than zero")

    # Consistent hashing via MD5 hex digest mapped to 10,000 buckets (0.01% precision)
    hash_key = f"{experiment_id}:{user_id}"
    digest = hashlib.md5(hash_key.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 10000

    cumulative = 0.0
    for variant in variants:
        fraction = variant["weight"] / total_weight
        cumulative += fraction * 10000
        if bucket < cumulative:
            return variant["name"]

    return variants[-1]["name"]


def get_or_assign_variant(
    db: Session,
    redis_client: redis.Redis,
    experiment: Experiment,
    user_id: str,
) -> Tuple[str, bool]:
    cache_key = f"assignment:{experiment.id}:{user_id}"

    # 1. Fast path: check Redis cache
    try:
        cached_variant = redis_client.get(cache_key)
        if cached_variant is not None:
            variant_str = cached_variant.decode("utf-8") if isinstance(cached_variant, bytes) else cached_variant
            return variant_str, True
    except redis.RedisError:
        # Gracefully degrade to DB if Redis is unreachable
        pass

    # 2. Cache miss: check PostgreSQL
    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.experiment_id == experiment.id,
            Assignment.user_id == user_id,
        )
        .first()
    )

    if assignment:
        variant = assignment.variant
    else:
        # 3. New user: deterministically compute variant and persist
        variant = compute_variant(
            experiment.id,
            user_id,
            experiment.variants,
        )
        try:
            assignment = Assignment(
                experiment_id=experiment.id,
                user_id=user_id,
                variant=variant,
            )
            db.add(assignment)
            db.commit()
        except IntegrityError:
            db.rollback()
            # Handle concurrent assignment race condition
            existing = (
                db.query(Assignment)
                .filter(
                    Assignment.experiment_id == experiment.id,
                    Assignment.user_id == user_id,
                )
                .first()
            )
            variant = existing.variant if existing else variant

    # 4. Write-back to Redis cache with TTL
    try:
        redis_client.setex(cache_key, settings.cache_ttl_seconds, variant)
    except redis.RedisError:
        pass

    return variant, False
