# app/schemas/simulation.py
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import date
from app.schemas.priority import PlanPriority
# 지연 임포트 처리: 나중에 임포트하는 방식으로 처리
class SimulationAsset(BaseModel):
    amount: float      # 총액
    principal: float   # 원금
    interest: float    # 수익(이자)

class SimulationDefault(BaseModel):
    """시뮬레이션 기본 설정 값 (Fallback용)"""
    default_interest: float = 0.02
    default_roi: float = 0.0
    default_dividend: float = 0.0
    inflation: float = 0.0

class SimulationRequest(BaseModel):
    plan_id: int
    default_value: SimulationDefault  # ✅ 묶어서 관리
    
    extra_monthly_spend: float = 0.0
    savings_rate: float = 0.3         # 필요 시 추가
    retirement_year: int
    expected_death_year: int
    priority: Optional[PlanPriority] = None

    
class SimulationPoint(BaseModel):
    month_index: int
    date: date
    net_worth: float
    net_cash_flow:float

    # 공통 규격(SimulationAsset) 사용
    savings: List[SimulationAsset]
    investments: List[SimulationAsset]
    debts: List[SimulationAsset]
    assets: List[SimulationAsset]
    others: float

    # ✅ 확장용: 버킷별 잔액
    buckets: Dict[str, float]


class SimulationResult(BaseModel):
    plan_id: int
    years: int
    points: List[SimulationPoint]
