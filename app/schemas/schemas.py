from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import date, datetime

# ===== Enums (DB ENUM과 1:1 매핑, 대문자 사용 권장) =====
Currency = Literal["KRW", "USD", "JPY", "EUR"]
Compound = Literal["SIMPLE", "COMPOUND"]
Gender   = Literal["MALE", "FEMALE", "OTHER"]
SavingType = Literal["DEPOSIT", "INSTALLMENT", "CASH", "SUBSCRIPTION"]
InvestType = Literal["STOCK", "BOND", "ETF", "FUND", "CRYPTO"]
AssetType  = Literal["HOUSE", "JEWELRY", "REAL_ESTATE"]
DebtType   = Literal["STUDENT_LOAN", "CREDIT_LOAN", "LIVING_EXPENSE_LOAN", "MORTGAGE"]
RevenueType = Literal["INCOME"]
ExpenseType = Literal["EXPENSE"]
TaxType     = Literal["INCOME_TAX"]

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
    name: Optional[str] = None
    amount: float = 0
    interest_rate: Optional[float] = None
    currency: Currency = "KRW"

class SavingUpdate(BaseModel):
    category: Optional[SavingType] = None
    name: Optional[str] = None
    amount: Optional[float] = None
    interest_rate: Optional[float] = None
    currency: Optional[Currency] = None

class SavingOut(BaseModel):
    id: int
    user_id: int
    category: SavingType
    name: Optional[str]
    amount: float
    interest_rate: Optional[float]
    currency: Currency
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

# ===== Investments =====
class InvestmentCreate(BaseModel):
    category: InvestType
    name: Optional[str] = None
    amount: float = 0
    yield_rate: Optional[float] = None
    currency: Currency = "KRW"

class InvestmentUpdate(BaseModel):
    category: Optional[InvestType] = None
    name: Optional[str] = None
    amount: Optional[float] = None
    yield_rate: Optional[float] = None
    currency: Optional[Currency] = None

class InvestmentOut(BaseModel):
    id: int
    user_id: int
    category: InvestType
    name: Optional[str]
    amount: float
    yield_rate: Optional[float]
    currency: Currency
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

# ===== Assets =====
class AssetCreate(BaseModel):
    category: AssetType
    has_loan: bool = False
    interest_rate: Optional[float] = None
    yield_rate: Optional[float] = None
    purchase_amount: Optional[float] = None
    purchase_ccy: Optional[Currency] = None
    current_amount: Optional[float] = None
    current_ccy: Optional[Currency] = None
    loan_amount: Optional[float] = None
    loan_ccy: Optional[Currency] = None
    repay_amount: Optional[float] = None
    repay_ccy: Optional[Currency] = None

class AssetUpdate(BaseModel):
    category: Optional[AssetType] = None
    has_loan: Optional[bool] = None
    interest_rate: Optional[float] = None
    yield_rate: Optional[float] = None
    purchase_amount: Optional[float] = None
    purchase_ccy: Optional[Currency] = None
    current_amount: Optional[float] = None
    current_ccy: Optional[Currency] = None
    loan_amount: Optional[float] = None
    loan_ccy: Optional[Currency] = None
    repay_amount: Optional[float] = None
    repay_ccy: Optional[Currency] = None

class AssetOut(BaseModel):
    id: int
    user_id: int
    category: AssetType
    has_loan: bool
    interest_rate: Optional[float]
    yield_rate: Optional[float]
    purchase_amount: Optional[float]
    purchase_ccy: Optional[Currency]
    current_amount: Optional[float]
    current_ccy: Optional[Currency]
    loan_amount: Optional[float]
    loan_ccy: Optional[Currency]
    repay_amount: Optional[float]
    repay_ccy: Optional[Currency]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

# ===== Debts =====
class DebtCreate(BaseModel):
    category: DebtType
    loan_amount: float
    loan_ccy: Optional[Currency] = "KRW"
    repay_amount: float
    repay_ccy: Optional[Currency] = "KRW"
    interest_rate: float
    compound: Optional[Compound] = "COMPOUND"
    currency: Optional[Currency] = "KRW"

class DebtUpdate(BaseModel):
    category: Optional[DebtType] = None
    loan_amount: Optional[float] = None
    loan_ccy: Optional[Currency] = None
    repay_amount: Optional[float] = None
    repay_ccy: Optional[Currency] = None
    interest_rate: Optional[float] = None
    compound: Optional[Compound] = None
    currency: Optional[Currency] = None

class DebtOut(BaseModel):
    id: int
    user_id: int
    category: DebtType
    loan_amount: float
    loan_ccy: Optional[Currency]
    repay_amount: float
    repay_ccy: Optional[Currency]
    interest_rate: float
    compound: Compound
    currency: Currency
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

# ===== Plans =====
class PlanCreate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

class PlanUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

class PlanOut(BaseModel):
    id: int
    user_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ===== Revenues (plan에 종속) =====
class RevenueCreate(BaseModel):
    plan_id: int
    category: RevenueType
    amount: float
    currency: Currency = "KRW"
    frequency: Optional[str] = None  # 예: "MONTHLY", "YEARLY", "ONE_OFF"
    time_range: Optional[str] = None # 예: "2024-01 ~ 2024-12"

class RevenueUpdate(BaseModel):
    category: Optional[RevenueType] = None
    amount: Optional[float] = None
    currency: Optional[Currency] = None
    frequency: Optional[str] = None
    time_range: Optional[str] = None

class RevenueOut(BaseModel):
    id: int
    plan_id: int
    category: RevenueType
    amount: float
    currency: Currency
    frequency: Optional[str]
    time_range: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

# ===== Taxes (plan에 종속) =====
class TaxCreate(BaseModel):
    plan_id: int
    category: TaxType

class TaxUpdate(BaseModel):
    category: Optional[TaxType] = None

class TaxOut(BaseModel):
    id: int
    plan_id: int
    category: TaxType
    created_at: Optional[datetime]
    updated_at: Optional[datetime]