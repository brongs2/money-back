# app/schemas/simulation.py
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import date
from app.schemas.priority import PlanPriority
# 지연 임포트 처리: 나중에 임포트하는 방식으로 처리

class SimulationRequest(BaseModel):
    plan_id: int

    expected_saving_interest: float  # 연간(소수). 예: 0.02
    expected_invest_return: float    # 연간(소수). 예: 0.05 (여기엔 "실질 수익률" 넣을 예정)
    extra_monthly_spend: float
    retirement_year: int
    expected_death_year :int
    savings_rate: float = 0.3  # priority 없을 때 fallback

    # ✅ priority 전달
    priority: Optional[PlanPriority] = None


class SimulationPoint(BaseModel):
    month_index: int
    date: date
    total_assets: float
    total_debts: float
    net_worth: float

    cash_like: float
    investments: float
    others: float

    # ✅ 확장용: 버킷별 잔액
    buckets: Dict[str, float]


class SimulationResult(BaseModel):
    plan_id: int
    years: int
    points: List[SimulationPoint]
