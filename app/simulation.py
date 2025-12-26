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
    def __repr__(self):
        total = self.principal + self.interest
        return f"<{self.asset_type}({self.category}): 원금={self.principal:,.0f}, 잔액={total:,.0f}>"
    
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
    default_roi = f(req.default_value.default_roi)
    default_dividend = f(req.default_value.default_dividend)
    default_interest = f(req.default_value.default_interest)
    inflation_rate = f(req.default_value.inflation)

    # 1. 저축 트래커
    saving_trackers = [
        AssetTracker(f(r["amount"]), r.get("category", "SAVINGS"), "SAVINGS", 
                     annual_rate=f(r.get("interest_rate")) or default_interest)
        for r in snapshot.get("savings", [])
    ]
    
    # 2. 투자 트래커
    invest_trackers = [
        AssetTracker(f(r["amount"]), r.get("category", "INVEST"), "INVEST", 
                     annual_rate=(f(r.get("roi")) or default_roi) - inflation_rate,
                     dividend_rate=f(r.get("dividend")) or default_dividend)
        for r in snapshot.get("investments", [])
    ]
    
    # 3. 개별 부채 트래커 (repay_amount 정보를 함께 저장)
    debt_trackers = []
    for r in snapshot.get("debts", []):
        tracker = AssetTracker(f(r["loan_amount"]), r.get("category", "DEBT"), "DEBT", 
                              annual_rate=f(r.get("interest_rate")))
        tracker.monthly_repay = f(r.get("repay_amount")) # 매달 고정 상환액
        debt_trackers.append(tracker)
    
    # 4. 고정 자산 트래커 (연결된 대출 상환액 정보 포함)
    asset_trackers = []
    asset_loan_trackers = [] # 자산에 딸린 대출을 별도 트래커로 관리
    for r in snapshot.get("assets", []):
        a_tracker = AssetTracker(f(r["amount"]), r.get("category", "ASSET"), "ASSET", 
                                annual_rate=(f(r.get("roi")) or 0.0) - inflation_rate,
                                dividend_rate=f(r.get("dividend")) or 0.0)
        asset_trackers.append(a_tracker)
        
        # 자산에 대출이 있는 경우 부채 트래커 생성
        loan_amt = f(r.get("loan_amount"))
        if loan_amt > 0:
            l_tracker = AssetTracker(loan_amt, f"{r.get('category')} 대출", "DEBT", 
                                    annual_rate=f(r.get("interest_rate")))
            l_tracker.monthly_repay = f(r.get("repay_amount"))
            asset_loan_trackers.append(l_tracker)
    # 잉여금 트래커
    extra_savings_tracker = AssetTracker(0.0, "잉여 저축", "SAVINGS", annual_rate=default_interest)
    extra_invest_tracker = AssetTracker(0.0, "잉여 투자", "INVEST", 
                                        annual_rate=default_roi - inflation_rate,
                                        dividend_rate=default_dividend)

    # 모든 부채 트래커 통합 (정렬 및 상환용)
    all_debt_trackers = debt_trackers + asset_loan_trackers

    # --- [2단계: 월간 기본 수입/지출] ---
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

    # --- [3단계: 시뮬레이션 루프] ---
    points = []
    current_date = start_date

    while current_date.year <= req.expected_death_year:
        # 1. 초기 현금 흐름 (수입 - 지출 + 배당금)
        income = monthly_income if current_date.year < req.retirement_year else 0.0
        total_dividend = sum(t.get_monthly_dividend() for t in invest_trackers + asset_trackers + [extra_invest_tracker])
        cash_flow = income - monthly_spend + total_dividend
        # 2. 필수 부채 상환 (repay_amount 차감)
        # 매달 고정적으로 나가는 원리금 상환액을 현금흐름에서 먼저 뺍니다.
        for d in all_debt_trackers:
            if d.principal <= 0: continue
            
            repayment = min(d.principal, d.monthly_repay)
            d.principal -= repayment
            cash_flow -= repayment

        # 시각화를 위한 순수 현금 흐름 기록 (부채 상환 후의 가용 자금)
        available_cash = cash_flow
        print(f"현재 날짜: {current_date}, 가용 현금: {available_cash:,.0f}")
        for d in debt_trackers + asset_loan_trackers:
            print(d)
        # 3. 잉여금 배분 또는 적자 보전
        if cash_flow > 0:
            monthly_surplus = cash_flow
            for alloc in req.priority.allocations:
                amount_to_push = monthly_surplus * alloc.weight
                
                if alloc.type == "SAVINGS":
                    extra_savings_tracker.add_principal(amount_to_push)
                elif alloc.type == "INVEST":
                    extra_invest_tracker.add_principal(amount_to_push)
                elif alloc.type == "DEBT":
                    # 이율 높은 순으로 추가 조기 상환 (Debt Avalanche)
                    high_int_debts = sorted([d for d in all_debt_trackers if d.principal > 0], 
                                          key=lambda x: x.monthly_rate, reverse=True)
                    debt_budget = amount_to_push
                    for d in high_int_debts:
                        if debt_budget <= 0: break
                        pay = min(d.principal, debt_budget)
                        d.principal -= pay
                        debt_budget -= pay
                    if debt_budget > 0: # 빚 다 갚고 남은 예산은 저축으로
                        extra_savings_tracker.add_principal(debt_budget)
            cash_flow = 0.0
        else:
            # 적자 발생 시 자산 인출 순서
            deficit = -cash_flow
            for tracker in ([extra_savings_tracker] + saving_trackers + [extra_invest_tracker] + invest_trackers):
                if deficit <= 0: break
                available = tracker.principal + tracker.interest
                take = min(available, deficit)
                tracker.subtract_total(take)
                deficit -= take

        # 4. 가치 성장 (이자 및 ROI 적용)
        all_trackers = saving_trackers + invest_trackers + all_debt_trackers + asset_trackers + \
                       [extra_savings_tracker, extra_invest_tracker]
        for t in all_trackers:
            t.apply_growth()

        # 5. 데이터 포인트 생성
        savings_res = [s.to_schema() for s in saving_trackers] + [extra_savings_tracker.to_schema()]
        invest_res = [i.to_schema() for i in invest_trackers] + [extra_invest_tracker.to_schema()]
        debt_res = [d.to_schema() for d in all_debt_trackers]
        asset_res = [a.to_schema() for a in asset_trackers]

        points.append(SimulationPoint(
            month_index=(current_date.year - start_date.year) * 12 + current_date.month - 1,
            date=current_date,
            savings=savings_res,
            investments=invest_res,
            debts=debt_res,
            assets=asset_res,
            net_worth=round(sum(s.amount for s in savings_res + invest_res + asset_res) - sum(d.amount for d in debt_res), 2),
            net_cash_flow=round(available_cash, 2), # 가용 현금 흐름 기록
            others=0.0,
            buckets={}
        ))
        current_date += relativedelta(months=1)

    return SimulationResult(plan_id=req.plan_id, years=len(points)//12, points=points)

def get_yearly_summary(sim_result):
    yearly_map = {}
    
    for p in sim_result.points:
        year = p.date.year
        if year not in yearly_map:
            yearly_map[year] = {
                "date": str(year),
                "net_worth": 0.0,
                "total_savings": 0.0,
                "total_investments": 0.0,
                "total_debts": 0.0,
                "total_assets": 0.0,
                "net_cash_flow": 0.0
            }
        
        # 자산 상태: 해당 연도의 마지막 데이터로 갱신 (Snapshot)
        yearly_map[year]["net_worth"] = float(p.net_worth)
        yearly_map[year]["total_savings"] = sum(s.amount for s in p.savings)
        yearly_map[year]["total_investments"] = sum(i.amount for i in p.investments)
        yearly_map[year]["total_debts"] = sum(d.amount for d in p.debts)
        yearly_map[year]["total_assets"] = sum(a.amount for a in p.assets)
        
        # 현금 흐름: 해당 연도의 모든 달을 합산 (Aggregate)
        yearly_map[year]["net_cash_flow"] += float(p.net_cash_flow)

    sorted_years = sorted(yearly_map.keys())
    
    return {
        "labels": [yearly_map[y]["date"] for y in sorted_years],
        "net_worth": [yearly_map[y]["net_worth"] for y in sorted_years],
        "total_savings": [yearly_map[y]["total_savings"] for y in sorted_years],
        "total_investments": [yearly_map[y]["total_investments"] for y in sorted_years],
        "total_debts": [yearly_map[y]["total_debts"] for y in sorted_years],
        "total_assets": [yearly_map[y]["total_assets"] for y in sorted_years],
        "net_cash_flow": [yearly_map[y]["net_cash_flow"] for y in sorted_years]
    }