from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, List, Any, Dict
from datetime import date, datetime
from app.simulation import SimulationResult
from app.schemas.priority import PlanPriority

# ===== Enums (Currency 제거) =====
Compound = Literal["COMPOUND", "SIMPLE"]
Gender   = Literal["MALE", "FEMALE", "OTHER"]
SavingType = Literal["DEPOSIT", "INSTALLMENT", "CASH", "SUBSCRIPTION"]
InvestType = Literal["STOCK", "BOND", "ETF", "FUND", "CRYPTO"]
AssetType  = Literal["HOUSE", "JEWELRY", "REAL_ESTATE"]
DebtType   = Literal["STUDENT_LOAN", "CREDIT_LOAN", "LIVING_EXPENSE_LOAN", "MORTGAGE"]
RevenueType = Literal["INCOME"]
ExpenseType = Literal["EXPENSE"]
TaxType     = Literal["INCOME_TAX"]
FrequencyType = Literal["YEARLY", "MONTHLY", "WEEKLY", "DAILY"]
PriorityBucketType = Literal["SAVINGS", "INVEST", "SPEND", "OTHER"]

# ===== Users =====
class UserCreate(BaseModel):
    username: str = Field(..., min_length=1)
    birth: Optional[date] = None
    gender: Optional[Gender] = None

class UserOut(BaseModel):
    id: int
    username: str
    birth: Optional[date] = None
    gender: Optional[Gender] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# ===== Savings =====
class SavingCreate(BaseModel):
    category: SavingType
    amount: float = 0
    interest_rate: Optional[float] = None
    compound: Optional[Compound] = "COMPOUND"
    deposit: Optional[float] = 0.0
    deposit_frequency: Optional[FrequencyType] = None
    maturity_date: Optional[date] = None

class SavingUpdate(BaseModel):
    category: Optional[SavingType] = None
    amount: Optional[float] = None
    interest_rate: Optional[float] = None
    compound: Optional[Compound] = None
    deposit: Optional[float] = None
    deposit_frequency: Optional[FrequencyType] = None
    maturity_date: Optional[date] = None

class SavingOut(BaseModel):
    id: int
    user_id: int
    category: SavingType
    amount: float
    interest_rate: Optional[float]
    compound: Optional[Compound] = None
    deposit: Optional[float] = 0.0
    deposit_frequency: Optional[FrequencyType] = None
    maturity_date: Optional[date] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

# ===== Investments =====
class InvestmentCreate(BaseModel):
    category: InvestType
    amount: float = 0
    roi: Optional[float] = None
    dividend: Optional[float] = 0.0
    deposit: Optional[float] = 0.0
    deposit_frequency: Optional[FrequencyType] = None
    maturity_date: Optional[date] = None

class InvestmentUpdate(BaseModel):
    category: Optional[InvestType] = None
    amount: Optional[float] = None
    roi: Optional[float] = None
    dividend: Optional[float] = None
    deposit: Optional[float] = None
    deposit_frequency: Optional[FrequencyType] = None
    maturity_date: Optional[date] = None

class InvestmentOut(BaseModel):
    id: int
    user_id: int
    category: InvestType
    amount: float
    roi: Optional[float]
    dividend: Optional[float]
    deposit: Optional[float] = 0.0
    deposit_frequency: Optional[FrequencyType] = None
    maturity_date: Optional[date] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

# ===== Assets (DB 컬럼 구조에 맞게 최적화) =====
class AssetCreate(BaseModel):
    category: AssetType
    interest_rate: Optional[float] = 0.0  # 대출 이율
    roi: Optional[float] = 0.0            # 자산 상승률
    dividend: Optional[float] = 0.0       # 배당/임대 수익률 (추가)
    amount: float = 0.0                   # 자산 가치 (purchase/current 통합)
    loan_amount: Optional[float] = 0.0    # 대출 원금
    repay_amount: Optional[float] = 0.0   # 월 상환액

class AssetUpdate(BaseModel):
    category: Optional[AssetType] = None
    interest_rate: Optional[float] = None
    roi: Optional[float] = None
    dividend: Optional[float] = None
    amount: Optional[float] = None
    loan_amount: Optional[float] = None
    repay_amount: Optional[float] = None

class AssetOut(BaseModel):
    id: int
    user_id: int
    category: AssetType
    interest_rate: Optional[float]
    roi: Optional[float]
    dividend: Optional[float]
    amount: float
    loan_amount: Optional[float]
    repay_amount: Optional[float]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

# ===== Debts (Currency 필드 전체 제거) =====
class DebtCreate(BaseModel):
    category: DebtType
    loan_amount: float
    repay_amount: float
    interest_rate: float
    compound: Optional[Compound] = "COMPOUND"

class DebtUpdate(BaseModel):
    category: Optional[DebtType] = None
    loan_amount: Optional[float] = None
    repay_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    compound: Optional[Compound] = None

class DebtOut(BaseModel):
    id: int
    user_id: int
    category: DebtType
    loan_amount: float
    repay_amount: float
    interest_rate: float
    compound: Compound
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

# ===== Revenues (start_date, end_date 추가) =====
class RevenueCreate(BaseModel):
    plan_id: int
    category: RevenueType
    amount: float
    frequency: FrequencyType
    start_date: Optional[date] = Field(None, description="수입 시작일")
    end_date: Optional[date] = Field(None, description="수입 종료일")

class RevenueUpdate(BaseModel):
    category: Optional[RevenueType] = None
    amount: Optional[float] = None
    frequency: Optional[FrequencyType] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class RevenueOut(BaseModel):
    id: int
    plan_id: int
    category: RevenueType
    amount: float
    frequency: FrequencyType
    start_date: Optional[date]
    end_date: Optional[date]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


# ===== Expenses (start_date, end_date 추가) =====
class ExpenseCreate(BaseModel):
    plan_id: int
    category: ExpenseType
    amount: float
    frequency: FrequencyType
    start_date: Optional[date] = Field(None, description="지출 시작일")
    end_date: Optional[date] = Field(None, description="지출 종료일")

class ExpenseUpdate(BaseModel):
    category: Optional[ExpenseType] = None
    amount: Optional[float] = None
    frequency: Optional[FrequencyType] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class ExpenseOut(BaseModel):
    id: int
    plan_id: int
    category: ExpenseType
    amount: float
    frequency: FrequencyType
    start_date: Optional[date]
    end_date: Optional[date]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
# ===== Taxes =====

class TaxCreate(BaseModel):
    category: TaxType
    rate: float = 0.0          # 세금 비율 (%)
    frequency: FrequencyType = "YEARLY"  # 기본값 연 단위로 설정

class TaxUpdate(BaseModel):
    category: Optional[TaxType] = None
    rate: Optional[float] = None
    frequency: Optional[FrequencyType] = None

class TaxOut(BaseModel):
    id: int
    plan_id: int
    category: TaxType
    rate: float
    frequency: FrequencyType
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

# ===== Plans =====
class PlanCreate(BaseModel):
    title: str
    description: Optional[str] = None
    roi: Optional[float] = None
    dividend: Optional[float] = None
    inflation: Optional[float] = None
    retirement_year: int
    expected_death_year: int
    priority: Optional[PlanPriority] = None

class PlanUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    retirement_year: Optional[int] = None       # 필수 해제
    expected_death_year: Optional[int] = None   # 필수 해제
    roi: Optional[float] = None
    dividend: Optional[float] = None
    inflation: Optional[float] = None
    priority: Optional[PlanPriority] = None

class PlanOut(BaseModel):
    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    retirement_year: int
    expected_death_year: int
    roi: Optional[float] = None
    dividend: Optional[float] = None
    inflation: Optional[float] = None
    priority: Optional[PlanPriority] = None
    created_at: datetime
    updated_at: datetime