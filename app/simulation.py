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

def calculate_monthly(rows):
    """수입/지출 목록을 받아 월평균 금액으로 환산"""
    total = 0.0
    for r in rows:
        amt, freq = f(r["amount"]), r.get("frequency", "MONTHLY")
        if freq == "MONTHLY": total += amt
        elif freq == "YEARLY": total += amt / 12.0
        elif freq == "WEEKLY": total += amt * (52 / 12)
        elif freq == "DAILY": total += amt * 30
        else: total += amt
    return total
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
    # --- [1단계: 트래커 및 설정 초기화] ---
    default_roi = float(req.default_value.default_roi or 0.0)
    default_dividend = float(req.default_value.default_dividend or 0.0)
    default_interest = float(req.default_value.default_interest or 0.0)
    inflation_rate = float(req.default_value.inflation or 0.0)
    emergency_debt_interest = 5.0  # 비상 대출 연이율

    # 1. 저축 트래커
    saving_trackers = []
    for r in snapshot.get("savings", []):
        t = AssetTracker(
            amount=float(r["amount"] or 0.0),
            category=r.get("category", "SAVINGS"),
            asset_type="SAVINGS",
            annual_rate=float(r.get("interest_rate") or default_interest),
            compound=r.get("compound", "COMPOUND")
        )
        t.deposit = float(r.get("deposit") or 0.0)
        t.maturity_date = r.get("maturity_date")
        saving_trackers.append(t)

    # 2. 투자 트래커 (ROI에서 인플레이션을 차감하여 실질 가치 계산)
    invest_trackers = []
    for r in snapshot.get("investments", []):
        t = AssetTracker(
            amount=float(r["amount"] or 0.0),
            category=r.get("category", "INVEST"),
            asset_type="INVEST",
            annual_rate=float(r.get("roi") or default_roi) - inflation_rate,
            dividend_rate=float(r.get("dividend") or default_dividend)
        )
        t.deposit = float(r.get("deposit") or 0.0)
        t.maturity_date = r.get("maturity_date")
        invest_trackers.append(t)
    
    # 3. 고정 부채 트래커
    debt_trackers = []
    for r in snapshot.get("debts", []):
        t = AssetTracker(
            amount=float(r["loan_amount"] or 0.0),
            category=r.get("category", "DEBT"),
            asset_type="DEBT",
            annual_rate=float(r.get("interest_rate") or 0.0)
        )
        t.monthly_repay = float(r.get("repay_amount") or 0.0)
        debt_trackers.append(t)

    # 4. 부동산 및 고정 자산 트래커
    asset_trackers = []
    asset_loan_trackers = []
    for r in snapshot.get("assets", []):
        # 자산 본체
        a_tracker = AssetTracker(
            amount=float(r["amount"] or 0.0),
            category=r.get("category", "ASSET"),
            asset_type="ASSET",
            annual_rate=float(r.get("roi") or 0.0) - inflation_rate,
            dividend_rate=float(r.get("dividend") or 0.0)
        )
        asset_trackers.append(a_tracker)
        # 해당 자산에 묶인 대출
        if float(r.get("loan_amount") or 0.0) > 0:
            l_tracker = AssetTracker(
                amount=float(r["loan_amount"] or 0.0),
                category=f"{r.get('category')} 대출",
                asset_type="DEBT",
                annual_rate=float(r.get("interest_rate") or 0.0)
            )
            l_tracker.monthly_repay = float(r.get("repay_amount") or 0.0)
            asset_loan_trackers.append(l_tracker)

    # 5. 잉여금/비상용 트래커
    extra_savings_tracker = AssetTracker(0.0, "잉여 저축", "SAVINGS", annual_rate=default_interest)
    extra_invest_tracker = AssetTracker(0.0, "잉여 투자", "INVEST", 
                                        annual_rate=default_roi - inflation_rate,
                                        dividend_rate=default_dividend)
    emergency_debt_tracker = AssetTracker(0.0, "비상 결제 부채", "DEBT", annual_rate=emergency_debt_interest)
    
    all_debt_trackers = debt_trackers + asset_loan_trackers + [emergency_debt_tracker]

    # --- [2단계: 수입/지출 전처리 (루프 밖 계산)] ---
    processed_revenues = []
    for r in snapshot.get("revenues", []):
        amt = float(r.get("amount") or 0.0)
        freq = r.get("frequency", "MONTHLY")
        if freq == "YEARLY": m_val = amt / 12.0
        elif freq == "WEEKLY": m_val = amt * (52 / 12)
        elif freq == "DAILY": m_val = amt * 30
        else: m_val = amt
        processed_revenues.append({
            "monthly_amt": m_val,
            "start": r.get("start_date") or start_date,
            "end": r.get("end_date") or date(req.expected_death_year, 12, 31),
            "category": r.get("category")
        })

    processed_expenses = []
    for e in snapshot.get("expenses", []):
        amt = float(e.get("amount") or 0.0)
        freq = e.get("frequency", "MONTHLY")
        if freq == "YEARLY": m_val = amt / 12.0
        elif freq == "WEEKLY": m_val = amt * (52 / 12)
        elif freq == "DAILY": m_val = amt * 30
        else: m_val = amt
        processed_expenses.append({
            "monthly_amt": m_val,
            "start": e.get("start_date") or start_date,
            "end": e.get("end_date") or date(req.expected_death_year, 12, 31)
        })
    # ✅ 세금 전처리 추가
    processed_taxes = []
    for t in snapshot.get("taxes", []):
        processed_taxes.append({
            "category": t.get("category"),
            "rate": float(t.get("rate") or 0.0) / 100.0, # %를 소수로 변환
            "frequency": t.get("frequency", "YEARLY")
        })
    # --- [3단계: 시뮬레이션 루프] ---
    points = []
    current_date = start_date

    while current_date.year <= req.expected_death_year:
        # 1. 만기 처리 (만기된 자산을 잉여 저축으로 이동)
        for t in (saving_trackers + invest_trackers):
            if t.maturity_date and current_date >= t.maturity_date:
                total_val = t.principal + t.interest
                extra_savings_tracker.add_principal(total_val)
                t.principal, t.interest, t.deposit = 0.0, 0.0, 0.0

        # 2. 이번 달 기초 수입/지출 계산
        this_month_income = 0.0
        for rev in processed_revenues:
            if rev["start"] <= current_date <= rev["end"]:
                if rev["category"] == "INCOME" and current_date.year >= req.retirement_year:
                    continue
                this_month_income += rev["monthly_amt"]
        # ✅ 2-1. 세금 계산 (INCOME_TAX 반영)
        this_month_tax = 0.0
        for tax in processed_taxes:
            if tax["category"] == "INCOME_TAX":
                # 소득세는 해당 월 수입에 세율을 곱함
                this_month_tax += (this_month_income * tax["rate"])


        this_month_spend = float(req.extra_monthly_spend or 0.0)
        for exp in processed_expenses:
            if exp["start"] <= current_date <= exp["end"]:
                this_month_spend += exp["monthly_amt"]

        # 3. 배당금 수익 합산
        this_month_dividend = sum(t.get_monthly_dividend() for t in invest_trackers + asset_trackers + [extra_invest_tracker])
        # print(this_month_dividend)
        # 4. 가용 현금흐름 확정 및 저축 불입
        cash_flow = this_month_income - this_month_spend + this_month_dividend
        this_month_deposit = 0.0
        
        for t in (saving_trackers + invest_trackers):
            if t.deposit > 0:
                # 현금이 부족하더라도 일단 약속된 저축을 실행 (현금흐름에서 차감)
                t.add_principal(t.deposit)
                cash_flow -= t.deposit
                this_month_deposit += t.deposit

        # 5. 필수 부채 상환
        this_month_repayment = 0.0
        for d in all_debt_trackers:
            if d.principal <= 0: continue
            repay_val = getattr(d, 'monthly_repay', 0.0)
            repayment = min(d.principal, repay_val)
            d.principal -= repayment
            cash_flow -= repayment
            this_month_repayment += repayment

        available_cash_before_extra = cash_flow

        # 6. 잉여금 처리 또는 적자(빚) 발생
        if cash_flow > 0:
            # 비상 부채가 있다면 우선 상환
            if emergency_debt_tracker.principal > 0:
                payback = min(emergency_debt_tracker.principal, cash_flow)
                emergency_debt_tracker.principal -= payback
                cash_flow -= payback
                this_month_repayment += payback
            
            # 남은 돈을 투자/저축 우선순위에 따라 배분
            if cash_flow > 0:
                for alloc in req.priority.allocations:
                    amount_to_push = cash_flow * alloc.weight
                    if alloc.type == "SAVINGS":
                        extra_savings_tracker.add_principal(amount_to_push)
                    elif alloc.type == "INVEST":
                        extra_invest_tracker.add_principal(amount_to_push)
                    elif alloc.type == "DEBT":
                        # 금리가 높은 부채부터 상환
                        high_int_debts = sorted([d for d in all_debt_trackers if d.principal > 0], 
                                              key=lambda x: x.monthly_rate, reverse=True)
                        debt_budget = amount_to_push
                        for d in high_int_debts:
                            pay = min(d.principal, debt_budget)
                            d.principal -= pay
                            debt_budget -= pay
                            this_month_repayment += pay
                        if debt_budget > 0:
                            extra_savings_tracker.add_principal(debt_budget)
        else:
            # 적자 발생 시 비상 부채 증가
            emergency_debt_tracker.add_principal(-cash_flow)

        # 7. 자산 가치 성장(이자/상승률) 적용
        all_trackers = saving_trackers + invest_trackers + all_debt_trackers + asset_trackers + \
                       [extra_savings_tracker, extra_invest_tracker]
        for t in all_trackers:
            t.apply_growth()

        # 8. 데이터 포인트 생성 및 저장
        savings_res = [s.to_schema() for s in saving_trackers] + [extra_savings_tracker.to_schema()]
        invest_res = [i.to_schema() for i in invest_trackers] + [extra_invest_tracker.to_schema()]
        debt_res = [d.to_schema() for d in all_debt_trackers]
        asset_res = [a.to_schema() for a in asset_trackers]

        points.append(SimulationPoint(
            month_index=(current_date.year - start_date.year) * 12 + current_date.month - start_date.month,
            date=current_date,
            savings=savings_res,
            investments=invest_res,
            debts=debt_res,
            assets=asset_res,
            net_worth=round(sum(s.amount for s in savings_res + invest_res + asset_res) - sum(d.amount for d in debt_res), 2),
            net_cash_flow=round(available_cash_before_extra, 2),
            repayment=round(this_month_repayment, 2),
            buckets={
                "total_income": round(this_month_income, 2),
                "total_spend": round(this_month_spend, 2),
                "total_dividend": round(this_month_dividend, 2),
                "total_deposit": round(this_month_deposit, 2),
                "total_tax": round(this_month_tax, 2)  # ✅ 세금 기록 추가
            }
        ))
        current_date += relativedelta(months=1)

    return SimulationResult(
        plan_id=req.plan_id, 
        years=len(points)//12, 
        points=points
    )



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
                "net_cash_flow": 0.0,
                "total_repayment": 0.0,
                "total_tax": 0.0,
                # ✅ 새롭게 추가된 상세 지표 초기화
                "total_income": 0.0,
                "total_spend": 0.0,
                "total_dividend": 0.0,
                "total_deposit": 0.0
            }
        
        # 1. 자산 상태 (Snapshot): 해당 연도의 마지막 달(12월) 데이터가 최종적으로 남음
        yearly_map[year]["net_worth"] = float(p.net_worth)
        yearly_map[year]["total_savings"] = sum(s.amount for s in p.savings)
        yearly_map[year]["total_investments"] = sum(i.amount for i in p.investments)
        yearly_map[year]["total_debts"] = sum(d.amount for d in p.debts)
        yearly_map[year]["total_assets"] = sum(a.amount for a in p.assets)
        # 2. 현금 흐름 (Aggregate): 해당 연도 12개월치를 모두 더함
        yearly_map[year]["net_cash_flow"] += float(p.net_cash_flow)
        yearly_map[year]["total_repayment"] += float(p.repayment)
        # ✅ buckets 내부의 상세 지표 합산
        if hasattr(p, 'buckets') and p.buckets:
            yearly_map[year]["total_income"] += float(p.buckets.get("total_income", 0))
            yearly_map[year]["total_spend"] += float(p.buckets.get("total_spend", 0))
            yearly_map[year]["total_dividend"] += float(p.buckets.get("total_dividend", 0))
            yearly_map[year]["total_deposit"] += float(p.buckets.get("total_deposit", 0))
            yearly_map[year]["total_tax"] += float(p.buckets.get("total_tax", 0)) # ✅ 세금 합산

    sorted_years = sorted(yearly_map.keys())
    print(yearly_map)
    # 리턴 딕셔너리에 상세 지표 리스트 추가
    return {
        "labels": [yearly_map[y]["date"] for y in sorted_years],
        "net_worth": [yearly_map[y]["net_worth"] for y in sorted_years],
        "total_savings": [yearly_map[y]["total_savings"] for y in sorted_years],
        "total_investments": [yearly_map[y]["total_investments"] for y in sorted_years],
        "total_debts": [yearly_map[y]["total_debts"] for y in sorted_years],
        "total_assets": [yearly_map[y]["total_assets"] for y in sorted_years],
        "net_cash_flow": [yearly_map[y]["net_cash_flow"] for y in sorted_years],
        "total_repayment": [yearly_map[y]["total_repayment"] for y in sorted_years],
        # ✅ HTML의 Chart/Table에서 사용할 리스트들
        "total_income": [yearly_map[y]["total_income"] for y in sorted_years],
        "total_spend": [yearly_map[y]["total_spend"] for y in sorted_years],
        "total_dividend": [yearly_map[y]["total_dividend"] for y in sorted_years],
        "total_deposit": [yearly_map[y]["total_deposit"] for y in sorted_years],
        "total_tax": [yearly_map[y]["total_tax"] for y in sorted_years]
    }