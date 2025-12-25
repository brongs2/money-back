from datetime import date
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Tuple, Optional
from app.schemas.simulation import SimulationRequest, SimulationResult, SimulationPoint, SimulationAsset

def f(x) -> float:
    """안전한 float 변환 헬퍼"""
    try:
        return float(x or 0.0)
    except (TypeError, ValueError):
        return 0.0

def _monthly_rate(annual_rate_pct: float) -> float:
    """연이율(%)을 월복리 이율로 변환"""
    rate = f(annual_rate_pct) / 100.0
    return (1.0 + rate) ** (1.0 / 12.0) - 1.0

class AssetTracker:
    def __init__(self, amount: float, category: str, asset_type: str, 
                 annual_rate: float = 0.0, dividend_rate: float = 0.0, compound: str = "COMPOUND"):
        self.category = category
        self.asset_type = asset_type
        self.compound = compound
        self.principal = amount
        self.interest = 0.0
        self.monthly_rate = _monthly_rate(annual_rate)
        self.monthly_dividend_rate = _monthly_rate(dividend_rate) # ✅ 월 배당률 변환
    def add_principal(self, amount: float):
        self.principal += amount

    def subtract_total(self, amount: float):
        if self.interest >= amount:
            self.interest -= amount
        else:
            remaining = amount - self.interest
            self.interest = 0.0
            self.principal = max(0.0, self.principal - remaining)

    def apply_growth(self):
        if self.asset_type == "DEBT":
            growth = self.principal * self.monthly_rate
            self.principal += growth
            return

        if self.compound == "SIMPLE":
            growth = self.principal * self.monthly_rate
        else:
            growth = (self.principal + self.interest) * self.monthly_rate
        
        self.interest += growth
    def get_monthly_dividend(self) -> float:
        """현재 총 자산에 대한 이번 달 배당금 계산"""
        # 자산 가치(원금+이자)의 월 배당률만큼 현금 발생
        return (self.principal + self.interest) * self.monthly_dividend_rate
    def to_schema(self) -> SimulationAsset:
        return SimulationAsset(
            amount=round(self.principal + self.interest, 2),
            principal=round(self.principal, 2),
            interest=round(self.interest, 2)
        )

def run_simulation(snapshot: dict, req: SimulationRequest, start_date: date) -> SimulationResult:
    # --- [1단계: 트래커 초기화] ---
    
    # 저축: 개별 이율이 없으면 req.default_value.default_interest 사용
    saving_trackers = [
        AssetTracker(
            f(r["amount"]), 
            r.get("category", "SAVINGS"), 
            "SAVINGS", 
            annual_rate=f(r.get("interest_rate")) or req.default_value.default_interest
        )
        for r in snapshot.get("savings", [])
    ]
    
    # 개별 yield_rate가 있으면 우선하고, 없으면 플랜의 실질 수익률 사용
    default_roi = f(req.default_value.default_roi) 
    default_dividend = f(req.default_value.default_dividend)

    invest_trackers = [
        AssetTracker(
            f(r["amount"]), 
            r.get("category", "INVEST"), 
            "INVEST", 
            annual_rate=f(r.get("roi")) or default_roi,
            dividend_rate=f(r.get("dividend")) or default_dividend

        )
        for r in snapshot.get("investments", [])
    ]
    
    debt_trackers = [
        AssetTracker(
            f(r["loan_amount"]), 
            "DEBT", 
            "DEBT", 
            annual_rate=f(r.get("interest_rate")), 
            compound=r.get("compound", "COMPOUND")
        )
        for r in snapshot.get("debts", [])
    ]
    
    asset_trackers = [
        AssetTracker(
            f(r["current_amount"]), 
            r.get("category", "ASSET"), 
            "ASSET", 
            annual_rate=f(r.get("yield_rate"))
        )
        for r in snapshot.get("assets", [])
    ]

    # 시뮬레이션 중 발생하는 잉여금을 담을 트래커
    extra_savings_tracker = AssetTracker(
        amount=0.0, 
        category="시뮬레이션 추가저축", 
        asset_type="SAVINGS", 
        annual_rate=req.default_value.default_interest
    )

    # --- [2단계: 월간 현금흐름 계산 함수] ---
    def calculate_monthly(rows):
        total = 0.0
        for r in rows:
            amt, freq = f(r["amount"]), r["frequency"]
            if freq == "MONTHLY": total += amt
            elif freq == "YEARLY": total += amt / 12.0
            elif freq == "WEEKLY": total += amt * (52 / 12)
            elif freq == "DAILY": total += amt * 30
            else: total += amt
        return total

    monthly_income = calculate_monthly(snapshot.get("revenues", []))
    monthly_spend = calculate_monthly(snapshot.get("expenses", [])) + f(req.extra_monthly_spend)
    
    total_repay_plan = sum(f(d["repay_amount"]) for d in snapshot.get("debts", [])) + \
                       sum(f(a["repay_amount"]) for a in snapshot.get("assets", []) if a["has_loan"])

    # --- [3단계: 시뮬레이션 루프] ---
    points = []
    current_date = start_date

    while current_date.year <= req.expected_death_year:
        income = monthly_income if current_date.year < req.retirement_year else 0.0
        base_cash_flow = income - monthly_spend
        # ✅ [추가] 모든 자산(투자, 일반자산 등)에서 발생하는 배당금 합산
        total_dividend_cash = sum(t.get_monthly_dividend() for t in invest_trackers + asset_trackers)
        
        # 최종 이번 달 가용 현금
        cash_flow = base_cash_flow + total_dividend_cash
        
        # --- [부채 상환 및 자산 배분 로직] ---
        # (기존과 동일: 부채 먼저 갚고, 남으면 extra_savings에 넣고, 모자라면 자산 인출)
        repay_needed = total_repay_plan
        for d in debt_trackers:
            if repay_needed <= 0 or d.principal <= 0: continue
            payment = min(d.principal, repay_needed)
            d.principal -= payment
            cash_flow -= payment
            repay_needed -= payment

        if cash_flow >= 0:
            extra_savings_tracker.add_principal(cash_flow)
        else:
            deficit = -cash_flow
            for tracker in ([extra_savings_tracker] + saving_trackers + invest_trackers):
                if deficit <= 0: break
                available = tracker.principal + tracker.interest
                take = min(available, deficit)
                tracker.subtract_total(take)
                deficit -= take

        # 모든 트래커 성장 적용 (성장률에는 ROI-Inflation만 반영됨)
        for t in (saving_trackers + invest_trackers + debt_trackers + asset_trackers + [extra_savings_tracker]):
            t.apply_growth()

        # 데이터 포인트 생성
        all_savings_schemas = [s.to_schema() for s in saving_trackers] + [extra_savings_tracker.to_schema()]
        invest_schemas = [i.to_schema() for i in invest_trackers]
        debt_schemas = [d.to_schema() for d in debt_trackers]
        asset_schemas = [a.to_schema() for a in asset_trackers]

        points.append(SimulationPoint(
            month_index=(current_date.year - start_date.year) * 12 + current_date.month - 1,
            date=current_date,
            savings=all_savings_schemas,
            investments=invest_schemas,
            debts=debt_schemas,
            assets=asset_schemas,
            net_worth=round(
                sum(s.amount for s in all_savings_schemas + invest_schemas + asset_schemas) - \
                sum(d.amount for d in debt_schemas), 2
            ),
            net_cash_flow=round(cash_flow, 2),
            others=0.0,
            buckets={}
        ))
        current_date += relativedelta(months=1)

    return SimulationResult(plan_id=req.plan_id, years=len(points)//12, points=points)