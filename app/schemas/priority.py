# app/schemas/schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Literal, Any
from datetime import datetime

# Priority 정의
PriorityBucketType = Literal["SAVINGS", "INVEST", "SPEND", "DEBT"]

class PriorityAllocation(BaseModel):
    bucket: str = Field(..., description="예: savings, invest, fun, emergency 등 자유롭게")
    type: PriorityBucketType = Field(..., description="버킷 타입")
    weight: float = Field(..., ge=0, description="0 이상 비율")

class PlanPriority(BaseModel):
    """
    allocations 합이 1.0이 되도록 권장(validator로 강제).
    """
    allocations: List[PriorityAllocation]

    @field_validator("allocations")
    @classmethod
    def validate_allocations(cls, v: List[PriorityAllocation]):
        if not v:
            raise ValueError("priority.allocations must not be empty")

        total = sum(a.weight for a in v)
        if total <= 0:
            raise ValueError("priority.allocations weights sum must be > 0")

        # 합 1.0 강제 (원하면 여기서 자동 normalize로 바꿀 수도 있음)
        if abs(total - 1.0) > 1e-6:
            raise ValueError("priority.allocations weights must sum to 1.0")

        # bucket 이름 중복 방지(원하면 허용 가능)
        buckets = [a.bucket for a in v]
        if len(buckets) != len(set(buckets)):
            raise ValueError("priority.allocations bucket names must be unique")

        return v