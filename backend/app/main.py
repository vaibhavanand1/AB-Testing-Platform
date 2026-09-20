from typing import List
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
import redis
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database import get_db, get_redis
from app.hashing import get_or_assign_variant
from app.models import Assignment, Event, Experiment
from app.schemas import (
    AssignmentResponse,
    EventCreate,
    EventResponse,
    ExperimentCreate,
    ExperimentResponse,
    ExperimentResultsResponse,
)
from app.stats import compute_experiment_results

app = FastAPI(
    title="A/B Testing Platform API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check(
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    db.execute(text("SELECT 1"))

    redis_ok = True
    try:
        redis_client.ping()
    except Exception:
        redis_ok = False

    return {
        "status": "ok",
        "database": "connected",
        "redis": "connected" if redis_ok else "disconnected",
    }


@app.post(
    "/experiments",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_experiment(
    payload: ExperimentCreate,
    db: Session = Depends(get_db),
):
    existing = db.query(Experiment).filter(Experiment.name == payload.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Experiment with name '{payload.name}' already exists",
        )

    experiment = Experiment(
        name=payload.name,
        variants=[v.model_dump() for v in payload.variants],
        status="active",
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    return experiment


@app.get(
    "/experiments",
    response_model=List[ExperimentResponse],
    status_code=status.HTTP_200_OK,
)
def list_experiments(
    db: Session = Depends(get_db),
):
    return db.query(Experiment).order_by(Experiment.created_at.desc()).all()


@app.get(
    "/experiments/{experiment_id}",
    response_model=ExperimentResponse,
    status_code=status.HTTP_200_OK,
)
def get_experiment(
    experiment_id: int,
    db: Session = Depends(get_db),
):
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )
    return experiment


@app.get(
    "/assign",
    response_model=AssignmentResponse,
    status_code=status.HTTP_200_OK,
)
def assign_user(
    experiment_id: int = Query(..., description="Target experiment ID"),
    user_id: str = Query(..., min_length=1, description="Unique user identifier"),
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )

    if experiment.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Experiment '{experiment.name}' is not active (status: {experiment.status})",
        )

    variant, from_cache = get_or_assign_variant(
        db=db,
        redis_client=redis_client,
        experiment=experiment,
        user_id=user_id,
    )

    return AssignmentResponse(
        experiment_id=experiment.id,
        user_id=user_id,
        variant=variant,
        from_cache=from_cache,
    )


@app.post(
    "/events",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
)
def track_event(
    payload: EventCreate,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    experiment = db.query(Experiment).filter(Experiment.id == payload.experiment_id).first()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {payload.experiment_id} not found",
        )

    # Resolve variant if not explicitly provided in payload
    variant = payload.variant
    if not variant:
        variant, _ = get_or_assign_variant(
            db=db,
            redis_client=redis_client,
            experiment=experiment,
            user_id=payload.user_id,
        )
    else:
        valid_variant_names = {v["name"] for v in experiment.variants}
        if variant not in valid_variant_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Variant '{variant}' is invalid for experiment '{experiment.name}'",
            )

    event = Event(
        experiment_id=payload.experiment_id,
        user_id=payload.user_id,
        variant=variant,
        event_type=payload.event_type,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@app.get(
    "/experiments/{experiment_id}/results",
    response_model=ExperimentResultsResponse,
    status_code=status.HTTP_200_OK,
)
def get_experiment_results(
    experiment_id: int,
    db: Session = Depends(get_db),
):
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )

    # 1. Aggregate unique visitor counts per variant
    assignment_rows = (
        db.query(Assignment.variant, func.count(Assignment.id))
        .filter(Assignment.experiment_id == experiment.id)
        .group_by(Assignment.variant)
        .all()
    )
    assignment_counts = {str(variant): int(count) for variant, count in assignment_rows}

    # 2. Aggregate unique conversions per variant
    conversion_rows = (
        db.query(Event.variant, func.count(func.distinct(Event.user_id)))
        .filter(
            Event.experiment_id == experiment.id,
            Event.event_type == "conversion",
        )
        .group_by(Event.variant)
        .all()
    )
    conversion_counts = {str(variant): int(count) for variant, count in conversion_rows}

    analysis = compute_experiment_results(
        variants=experiment.variants,
        assignment_counts=assignment_counts,
        conversion_counts=conversion_counts,
    )

    return ExperimentResultsResponse(
        experiment_id=experiment.id,
        experiment_name=experiment.name,
        status=experiment.status,
        variants=analysis["variants"],
        comparisons=analysis["comparisons"],
    )
