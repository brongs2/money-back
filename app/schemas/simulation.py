from pydantic import BaseModel
from typing import Optional, Literal
from datetime import date

class SimulationRequest(BaseModel):
    plan_id: Optional[int] = None          # 특정 플랜 기준으로 시뮬레이션 하고 싶으면
    months: int = 60                       # 몇 개월 시뮬레이션 할지
    extra_monthly_spend: float = 0         # 추가 소비(플랜 외)
    savings_rate: float = 0.0              # (선택) 소득 중 몇 % 저축/투자
    expected_saving_interest: float = 0.02 # 예: 연 2%
    expected_invest_return: float = 0.05   # 예: 연 5%
    expected_debt_interest_spread: float = 0.0  # (옵션) 부채 이자 조정치

class SimulationPoint(BaseModel):
    month_index: int
    date: date
    total_assets: float
    total_debts: float
    net_worth: float
    cash_like: float      # savings + 현금성
    investments: float
    others: float

class SimulationResult(BaseModel):
    plan_id: Optional[int]
    months: int
    points: list[SimulationPoint]
