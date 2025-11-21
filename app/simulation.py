from datetime import date
from dateutil.relativedelta import relativedelta  # 안 쓰면 직접 month 더해도 됨
from typing import List
from app.schemas.simulation import SimulationRequest, SimulationPoint, SimulationResult

def run_simulation(snapshot: dict, req: SimulationRequest, start_date: date) -> SimulationResult:
    # 초기 상태
    total_savings = sum(r["amount"] for r in snapshot["savings"])
    total_invest  = sum(r["amount"] for r in snapshot["investments"])
    total_debt    = sum(r["loan_amount"] for r in snapshot["debts"])

    # 월 이자율 / 수익률 (연 → 월)
    saving_r_month = (1 + req.expected_saving_interest) ** (1/12) - 1
    invest_r_month = (1 + req.expected_invest_return) ** (1/12) - 1

    # 단순화: revenues 전부 월소득으로 가정
    monthly_income = sum(r["amount"] for r in snapshot["revenues"])
    # 세금이나 소비는 일단 외부에서 넘겨준 extra_monthly_spend 사용
    monthly_spend  = req.extra_monthly_spend

    points: List[SimulationPoint] = []

    current_date = start_date
    for m in range(req.months):
        # 1) 소득 유입
        cash_flow = monthly_income - monthly_spend

        # 2) 부채 이자/상환
        monthly_debt_payment = sum(r["repay_amount"] for r in snapshot["debts"]) if snapshot["debts"] else 0.0
        total_debt = max(total_debt + total_debt * (0) - monthly_debt_payment, 0)  # 이자 0으로 두고 싶으면 이렇게, 아니면 로직 추가
        cash_flow -= monthly_debt_payment

        # 3) 캐시플로우를 저축/투자에 배분 (예: savings_rate 비율로 투자, 나머지는 저축)
        invest_add = cash_flow * req.savings_rate
        saving_add = cash_flow - invest_add

        total_savings += saving_add
        total_invest  += invest_add

        # 4) 이자/수익 반영
        total_savings *= (1 + saving_r_month)
        total_invest  *= (1 + invest_r_month)

        # 5) 순자산 계산
        total_assets = total_savings + total_invest  # assets table까지 쓰고 싶으면 더 합쳐도 됨
        net_worth = total_assets - total_debt

        points.append(
            SimulationPoint(
                month_index=m,
                date=current_date,
                total_assets=total_assets,
                total_debts=total_debt,
                net_worth=net_worth,
                cash_like=total_savings,
                investments=total_invest,
                others=0.0,
            )
        )

        current_date = current_date + relativedelta(months=1)

    return SimulationResult(
        plan_id=req.plan_id,
        months=req.months,
        points=points,
    )
