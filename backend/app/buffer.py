import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import redis

from app.config import settings

logger = logging.getLogger(__name__)


def build_exposure_payload(
    experiment_id: int,
    user_id: str,
    variant: str,
    metadata: Optional[Dict[str, Any]] = None,
    timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    ts = timestamp or datetime.now(timezone.utc)
    return {
        "experiment_id": experiment_id,
        "user_id": user_id,
        "variant": variant,
        "timestamp": ts.isoformat(),
        "metadata": metadata,
    }


def log_exposure_event(
    redis_client: redis.Redis,
    experiment_id: int,
    user_id: str,
    variant: str,
    metadata: Optional[Dict[str, Any]] = None,
    buffer_key: Optional[str] = None,
) -> bool:
    """
    Asynchronously and non-blockingly pushes an exposure event to the Redis buffer.
    Designed to execute in sub-millisecond time (<0.5ms) without waiting on PostgreSQL.
    """
    key = buffer_key or settings.exposure_buffer_key
    payload = build_exposure_payload(
        experiment_id=experiment_id,
        user_id=user_id,
        variant=variant,
        metadata=metadata,
    )
    try:
        redis_client.lpush(key, json.dumps(payload))
        return True
    except redis.RedisError as e:
        logger.error(f"Failed to push exposure event to Redis buffer '{key}': {e}")
        return False


def get_buffer_length(
    redis_client: redis.Redis,
    buffer_key: Optional[str] = None,
) -> int:
    key = buffer_key or settings.exposure_buffer_key
    try:
        return redis_client.llen(key)
    except redis.RedisError:
        return 0


def get_dlq_length(
    redis_client: redis.Redis,
    dlq_key: Optional[str] = None,
) -> int:
    key = dlq_key or settings.exposure_dlq_key
    try:
        return redis_client.llen(key)
    except redis.RedisError:
        return 0


def clear_exposure_buffers(
    redis_client: redis.Redis,
    buffer_key: Optional[str] = None,
    dlq_key: Optional[str] = None,
) -> None:
    b_key = buffer_key or settings.exposure_buffer_key
    d_key = dlq_key or settings.exposure_dlq_key
    try:
        redis_client.delete(b_key, d_key)
    except redis.RedisError:
        pass
