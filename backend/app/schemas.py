from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class VariantDef(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    weight: float = Field(..., gt=0)


class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    variants: List[VariantDef] = Field(..., min_length=2)

    @field_validator("variants")
    @classmethod
    def validate_variants(cls, variants: List[VariantDef]) -> List[VariantDef]:
        names = [v.name.strip().lower() for v in variants]
        if len(names) != len(set(names)):
            raise ValueError("Variant names must be unique within an experiment")

        total_weight = sum(v.weight for v in variants)
        if not (99.9 <= total_weight <= 100.1):
            raise ValueError(
                f"Total variant weight must sum to 100 (currently {total_weight:.1f})"
            )
        return variants


class ExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    variants: List[VariantDef]
    status: str
    created_at: datetime


class AssignmentResponse(BaseModel):
    experiment_id: int
    user_id: str
    variant: str
    from_cache: bool


class EventCreate(BaseModel):
    experiment_id: int
    user_id: str = Field(..., min_length=1, max_length=255)
    event_type: str = Field(default="conversion", min_length=1, max_length=100)
    variant: Optional[str] = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: int
    user_id: str
    variant: str
    event_type: str
    timestamp: datetime


class VariantResult(BaseModel):
    name: str
    weight: float
    sample_size: int
    conversions: int
    conversion_rate: float
    conversion_rate_percentage: float


class ComparisonResult(BaseModel):
    control_variant: str
    treatment_variant: str
    absolute_diff: float
    relative_lift_percentage: float
    z_score: float
    p_value: float
    confidence_interval: List[float]
    is_significant: bool
    peeking_guard_active: bool
    message: str


class ExperimentResultsResponse(BaseModel):
    experiment_id: int
    experiment_name: str
    status: str
    variants: List[VariantResult]
    comparisons: List[ComparisonResult]
