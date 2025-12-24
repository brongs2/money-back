# app/simulation.py
from datetime import date
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Tuple, Optional
from app.schemas.priority import PlanPriority
from app.schemas.simulation import SimulationRequest, SimulationResult, SimulationPoint

def f(x) -> float:
    try:
        return float(x or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_priority(req: SimulationRequest) -> List[Tuple[str, str, float]]:
    """
    반환: [(bucket_name, bucket_type, weight), ...]  (weight 합 = 1)
    priority가 없으면 savings_rate 기반 기본값 생성.
    """
    if req.priority and req.priority.allocations:
        allocs = [(a.bucket, a.type, float(a.weight)) for a in req.priority.allocations]
        s = sum(w for _, _, w in allocs)
        if s <= 0:
            # fallback
            invest = max(min(f(req.savings_rate), 1.0), 0.0)
            return [("invest", "INVEST", invest), ("savings", "SAVINGS", 1.0 - invest)]
        # 합이 1이 아닐 수도 있으니 안전 normalize (스키마에서 강제해도 runtime 방어)
        return [(b, t, w / s) for b, t, w in allocs]

    invest = max(min(f(req.savings_rate), 1.0), 0.0)
    return [("invest", "INVEST", invest), ("savings", "SAVINGS", 1.0 - invest)]


def _monthly_rate(annual_rate: float) -> float:
    return (1.0 + f(annual_rate)) ** (1.0 / 12.0) - 1.0


def run_simulation(snapshot: dict, req: SimulationRequest, start_date: date) -> SimulationResult:
    savings_rows = snapshot.get("savings", [])
    investment_rows = snapshot.get("investments", [])
    asset_rows = snapshot.get("assets", [])
    debt_rows = snapshot.get("debts", [])

    # 초기 자산
    total_savings = sum(f(r.get("amount")) for r in savings_rows)
    total_invest = sum(f(r.get("amount")) for r in investment_rows)
    total_debt = sum(f(r.get("loan_amount")) for r in debt_rows)
    total_assets_value = sum(f(r.get("current_amount")) for r in asset_rows)

    # 버킷 잔액(확장용)
    buckets: Dict[str, float] = {
        "savings": total_savings,
        "invest": total_invest,
    }

    saving_r_month = _monthly_rate(req.expected_saving_interest)
    invest_r_month = _monthly_rate(req.expected_invest_return)

    # 월수입(빈도 처리)
    monthly_income = 0.0
    for r in snapshot.get("revenues", []):
        freq = r.get("frequency")
        amt = f(r.get("amount"))
        if freq == "MONTHLY":
            monthly_income += amt
        elif freq == "YEARLY":
            monthly_income += amt / 12.0
        elif freq == "WEEKLY":
            monthly_income += amt * (52.0 / 12.0)
        elif freq == "DAILY":
            monthly_income += amt * 30.0
        else:
            monthly_income += amt

    # 월지출
    monthly_spend = f(req.extra_monthly_spend)
    for e in snapshot.get("expenses", []):
        freq = e.get("frequency")
        amt = f(e.get("amount"))
        if freq == "MONTHLY":
            monthly_spend += amt
        elif freq == "YEARLY":
            monthly_spend += amt / 12.0
        elif freq == "WEEKLY":
            monthly_spend += amt * (52.0 / 12.0)
        elif freq == "DAILY":
            monthly_spend += amt * 30.0
        else:
            monthly_spend += amt

    allocations = _normalize_priority(req)

    points: List[SimulationPoint] = []
    current_date = start_date

    # retirement_year 이후로 revenue는 없어짐
    retirement_year = req.retirement_year
    expected_death_year = req.expected_death_year

    # 1년 단위로 집계할 때 필요한 변수
    year_to_data = {}

    while current_date.year <= expected_death_year:
        current_year = current_date.year
        if current_year >= retirement_year:
            monthly_income = 0.0  # 퇴직 이후 수입은 없으므로

        # 기본 현금흐름
        cash_flow = monthly_income - monthly_spend

        # 부채 상환
        monthly_debt_payment = sum(f(r.get("repay_amount")) for r in debt_rows)
        total_debt = max(total_debt - monthly_debt_payment, 0.0)
        cash_flow -= monthly_debt_payment

        # cash_flow 배분 (priority에 따른 배분)
        if cash_flow >= 0:
            for bucket_name, bucket_type, w in allocations:
                portion = cash_flow * w

                if bucket_type == "SPEND":
                    continue  # 써버린 돈: 자산에 안 쌓임

                buckets[bucket_name] = buckets.get(bucket_name, 0.0) + portion
        else:
            # 적자 처리
            deficit = -cash_flow
            saving_bucket_names = [b for b, t, _ in allocations if t == "SAVINGS"]
            invest_bucket_names = [b for b, t, _ in allocations if t == "INVEST"]

            for b in saving_bucket_names:
                if deficit <= 0:
                    break
                available = buckets.get(b, 0.0)
                take = min(available, deficit)
                buckets[b] = available - take
                deficit -= take

            for b in invest_bucket_names:
                if deficit <= 0:
                    break
                available = buckets.get(b, 0.0)
                take = min(available, deficit)
                buckets[b] = available - take
                deficit -= take

        # 성장률 적용
        alloc_type_map = {b: t for b, t, _ in allocations}
        for b, t in alloc_type_map.items():
            if t == "SAVINGS":
                buckets[b] = buckets.get(b, 0.0) * (1.0 + saving_r_month)
            elif t == "INVEST":
                buckets[b] = buckets.get(b, 0.0) * (1.0 + invest_r_month)
            elif t == "OTHER":
                buckets[b] = buckets.get(b, 0.0)

        # 집계
        total_savings = sum(buckets.get(b, 0.0) for b, t, _ in allocations if t == "SAVINGS")
        total_invest = sum(buckets.get(b, 0.0) for b, t, _ in allocations if t == "INVEST")
        total_other_buckets = sum(buckets.get(b, 0.0) for b, t, _ in allocations if t == "OTHER")

        total_assets = total_savings + total_invest + total_other_buckets + total_assets_value
        net_worth = total_assets - total_debt

        # 1년 단위로 집계
        if current_year not in year_to_data:
            year_to_data[current_year] = {
                "total_assets": total_assets,
                "total_debts": total_debt,
                "net_worth": net_worth,
                "cash_like": total_savings,
                "investments": total_invest,
                "others": total_assets_value + total_other_buckets
            }

        # 1년 단위로 증가
        current_date = current_date + relativedelta(years=1)

    # 데이터를 1년 단위로 변환한 후 points 리스트에 추가
    for year, data in year_to_data.items():
        points.append(
            SimulationPoint(
                month_index=year,  # x축을 년도로 변경
                date=f"{year}-01-01",  # 첫날 날짜 설정
                total_assets=float(data["total_assets"]),
                total_debts=float(data["total_debts"]),
                net_worth=float(data["net_worth"]),
                cash_like=float(data["cash_like"]),
                investments=float(data["investments"]),
                others=float(data["others"]),
                buckets={}  # 1년 단위이므로 세부 버킷 정보는 생략
            )
        )
    print(points)
    # 'months' 대신 'years'로 변경
    return SimulationResult(plan_id=req.plan_id, years=len(points), points=points)
