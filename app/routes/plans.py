# app/api/routes/plans.py

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
import asyncpg
from fastapi import Request
from typing import Optional
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import json
from datetime import date

from app.db import get_db_connection
from app.schemas.schemas import (
    PlanCreate, PlanOut, PlanUpdate,
    RevenueCreate, RevenueOut, RevenueUpdate,
    ExpenseCreate, ExpenseOut, ExpenseUpdate,
    TaxCreate, TaxOut, TaxUpdate,
)
from app.schemas.schemas import PlanPriority
from app.schemas.simulation import SimulationRequest, SimulationDefault
from app.simulation import run_simulation
from app.snapshot import load_user_snapshot
from app.auth import get_current_user, CurrentUser  # 가정

router = APIRouter(prefix="/plans", tags=["plans"])

templates = Jinja2Templates(directory="app/templates")


def _to_rate_pct(v) -> float:
    """DB/요청에 저장된 % 값을 연간 rate(소수)로 변환. None이면 0."""
    try:
        return float(v or 0.0) / 100.0
    except (TypeError, ValueError):
        return 0.0


def _real_return(roi_pct, dividend_pct, inflation_pct) -> float:
    """
    실질 수익률(연간, 소수):
      real = ((1+roi)*(1+dividend))/(1+inflation) - 1
    (roi/dividend/inflation은 %로 들어온다고 가정)
    """
    roi = _to_rate_pct(roi_pct)
    div = _to_rate_pct(dividend_pct)
    inf = _to_rate_pct(inflation_pct)

    # inflation이 -100%에 가까운 이상값이면 방어
    denom = (1.0 + inf)
    if denom <= 0:
        denom = 1.0

    return ((1.0 + roi) * (1.0 + div)) / denom - 1.0


@router.post("/", response_model=PlanOut)
async def create_plan(
    payload: PlanCreate,
    current_user: CurrentUser = Depends(get_current_user),
    conn: Session = Depends(get_db_connection),
):
    title = payload.title
    description = payload.description

    # 추가된 컬럼들
    roi = getattr(payload, "roi", None)
    dividend = getattr(payload, "dividend", None)
    inflation = getattr(payload, "inflation", None)

    async with conn.transaction():
        # Plan 생성
        row = await conn.fetchrow(
            """
            INSERT INTO plans
                (user_id, title, roi, dividend, inflation, description, priority)
            VALUES
                ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, user_id, title, roi, dividend, inflation, description, priority, created_at, updated_at
            """,
            current_user.id, title, roi, dividend, inflation, description, payload.priority.json()  # priority를 JSON 형식으로 저장
        )

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "roi": row["roi"],
        "dividend": row["dividend"],
        "inflation": row["inflation"],
        "description": row["description"],
        "priority": row["priority"],  # priority 값도 반환
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }




@router.get("/{plan_id}")
async def get_plan_details(
    plan_id: int,
    request: Request,
    view: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    # Plan 조회
    plan = await conn.fetchrow(
        """
        SELECT id, user_id, title, roi, dividend, inflation, description, priority,retirement_year,  expected_death_year, created_at, updated_at
        FROM plans
        WHERE user_id = $1 AND id = $2
        """,
        current_user.id,
        plan_id,
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # priority 컬럼을 사용하여 데이터 가져오기 (JSONB 형식)
    priority = plan["priority"]  # priority 값 가져오기 (문자열 형태일 경우)
    print(priority)
    print(type(priority))

    # 만약 priority가 문자열이라면, 이를 JSON으로 로드하여 딕셔너리로 변환
    if isinstance(priority, str):
        priority = json.loads(priority)  # 문자열을 딕셔너리로 변환

    # PlanPriority로 변환
    plan_priority = PlanPriority(**priority)  # PlanPriority 객체로 변환

    # 나머지 로직 처리 (revenues, expenses 등)
    revenues = await conn.fetch(
        """
        SELECT category, amount, frequency
        FROM revenues
        WHERE plan_id = $1
        ORDER BY created_at DESC
        """,
        plan_id,
    )

    expenses = await conn.fetch(
        """
        SELECT category, amount, frequency
        FROM expenses
        WHERE plan_id = $1
        ORDER BY created_at DESC
        """,
        plan_id,
    )

    snapshot = await load_user_snapshot(conn, current_user.id)
    snapshot["revenues"] = list(revenues)
    snapshot["expenses"] = list(expenses)

    # 실질 수익률 계산

    sim_req = SimulationRequest(
        plan_id=plan["id"],
        default_value=SimulationDefault(
            default_interest=0.02,
            default_roi=plan["roi"],
            default_dividend=plan["dividend"],
            inflation=plan["inflation"]
        ),
        extra_monthly_spend=0.0,
        priority=plan_priority,
        retirement_year=plan["retirement_year"],
        expected_death_year=plan["expected_death_year"]
    )
    sim_result = run_simulation(snapshot, sim_req, start_date=date.today())
    labels = [p.date.strftime("%Y") for p in sim_result.points]
    total_assets = [sum(item.amount for item in p.assets) for p in sim_result.points]
    total_savings = [sum(item.amount for item in p.savings) for p in sim_result.points]
    total_investments = [sum(item.amount for item in p.investments) for p in sim_result.points]
    total_debts = [sum(item.amount for item in p.debts) for p in sim_result.points]
    net_worth = [float(p.net_worth) for p in sim_result.points]
        # 차트용 데이터 추출
    net_cash_flow = [float(p.net_cash_flow) for p in sim_result.points]
    if view == "html":
        return templates.TemplateResponse(
            "plan_detail.html",
            {
                "request": request,
                "plan": plan,
                "revenues": revenues,
                "expenses": expenses,
                "labels": labels,
                "net_worth": net_worth,
                "net_cash_flow": net_cash_flow,
                # ✅ HTML 템플릿에서 차트를 그리기 위해 아래 변수들이 반드시 필요합니다.
                "total_assets": total_assets,
                "total_savings": total_savings,
                "total_investments": total_investments,
                "total_debts": total_debts,
                "priority": plan_priority,
                "retirement_year": plan["retirement_year"],
                "expected_death_year": plan["expected_death_year"],
            },
        )

    return {
        "id": plan["id"],
        "user_id": plan["user_id"],
        "title": plan["title"],
        "roi": plan["roi"],
        "dividend": plan["dividend"],
        "inflation": plan["inflation"],
        "description": plan["description"],
        "priority": plan_priority,  # priority 반환
        "created_at": plan["created_at"],
        "updated_at": plan["updated_at"],
        "revenues": list(revenues),
        "expenses": list(expenses),
        "total_savings": total_savings,      # JSON 응답에 추가
        "total_investments": total_investments, # JSON 응답에 추가
        "total_debts": total_debts,          # JSON 응답에 추가
        "total_assets": total_assets,          # JSON 응답에 추가
        "labels": labels,
        "net_worth": net_worth,
        "retirement_year": plan["retirement_year"],
        "expected_death_year": plan["expected_death_year"],
    }

@router.patch("/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: int,
    payload: PlanUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    conn=Depends(get_db_connection),
):
    current = await conn.fetchrow(
        """
        SELECT
            id,
            user_id,
            title,
            roi,
            dividend,
            inflation,
            description,
            priority,
            retirement_year,
            expected_death_year,
            created_at,
            updated_at
        FROM plans
        WHERE id = $1 AND user_id = $2
        """,
        plan_id,
        current_user.id,
    )

    if not current:
        raise HTTPException(status_code=404, detail="Plan not found")

    new_title = payload.title if payload.title is not None else current["title"]
    new_description = payload.description if payload.description is not None else current["description"]
    new_roi = payload.roi if getattr(payload, "roi", None) is not None else current["roi"]
    new_dividend = payload.dividend if getattr(payload, "dividend", None) is not None else current["dividend"]
    new_inflation = payload.inflation if getattr(payload, "inflation", None) is not None else current["inflation"]
    new_retirement_year = payload.retirement_year if getattr(payload, "retirement_year", None) is not None else current["retirement_year"]
    new_expected_death_year = payload.expected_death_year if getattr(payload, "expected_death_year", None) is not None else current["expected_death_year"]

    # Priority 업데이트
    if payload.priority:
        allocations = payload.priority.dict()
        async with conn.transaction():
            # Priority 테이블 업데이트
            await conn.fetchrow(
                """
                UPDATE plans
                SET priority = $1
                WHERE id = $2 AND user_id = $3
                RETURNING id
                """,
                allocations,
                plan_id,
                current_user.id
            )

    # Plan 업데이트
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE plans
            SET
                title       = $1,
                description = $2,
                roi         = $5,
                dividend    = $6,
                inflation   = $7,
                retirement_year = $8,
                expected_death_year = $9,
                
                updated_at  = now()
            WHERE id = $3 AND user_id = $4
            RETURNING
                id,
                user_id,
                title,
                roi,
                dividend,
                inflation,
                description,
                retirement_year,
                expected_death_year,
                created_at,
                updated_at
            """,
            new_title,
            new_description,
            plan_id,
            current_user.id,
            new_roi,
            new_dividend,
            new_inflation,
            new_retirement_year,
            new_expected_death_year,
        )

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "roi": row["roi"],
        "dividend": row["dividend"],
        "inflation": row["inflation"],
        "description": row["description"],
        "priority": row["priority"],  # priority 추가
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "retirement_year": row["retirement_year"],
        "expected_death_year": row["expected_death_year"],
    }

# ----- Plan 삭제 -----
@router.delete("/{plan_id}", status_code=204)
async def delete_plan(
    plan_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    conn=Depends(get_db_connection),
):
    async with conn.transaction():
        result = await conn.execute(
            """
            DELETE FROM plans
            WHERE id = $1 AND user_id = $2
            """,
            plan_id,
            current_user.id,
        )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="plan not found")

    return Response(status_code=204)


# ==========================
# Plan 하위: Revenues
# ==========================

@router.post("/{plan_id}/revenues", response_model=RevenueOut)
async def create_revenue(
    plan_id: int,
    payload: RevenueCreate,
    conn=Depends(get_db_connection),
):
    category = payload.category
    amount = payload.amount
    currency = payload.currency
    frequency = payload.frequency
    time_range = payload.time_range

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO revenues
                (plan_id, category, amount, currency, frequency, time_range)
            VALUES
                ($1,      $2,       $3,     $4,       $5,        $6)
            RETURNING
                id,
                plan_id,
                category,
                amount,
                currency,
                frequency,
                time_range,
                created_at,
                updated_at
            """,
            plan_id,
            category,
            amount,
            currency,
            frequency,
            time_range,
        )

    return {
        "id": row["id"],
        "plan_id": row["plan_id"],
        "category": row["category"],
        "amount": row["amount"],
        "currency": row["currency"],
        "frequency": row["frequency"],
        "time_range": row["time_range"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("/{plan_id}/revenues", response_model=list[RevenueOut])
async def list_revenues(
    plan_id: int,
    conn=Depends(get_db_connection),
):
    rows = await conn.fetch(
        """
        SELECT
            id,
            plan_id,
            category,
            amount,
            currency,
            frequency,
            time_range,
            created_at,
            updated_at
        FROM revenues
        WHERE plan_id = $1
        ORDER BY created_at DESC
        """,
        plan_id,
    )

    return [
        {
            "id": row["id"],
            "plan_id": row["plan_id"],
            "category": row["category"],
            "amount": row["amount"],
            "currency": row["currency"],
            "frequency": row["frequency"],
            "time_range": row["time_range"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


@router.patch("/revenues/{revenue_id}", response_model=RevenueOut)
async def update_revenue(
    revenue_id: int,
    payload: RevenueUpdate,
    conn=Depends(get_db_connection),
):
    current = await conn.fetchrow(
        """
        SELECT
            id,
            plan_id,
            category,
            amount,
            currency,
            frequency,
            time_range,
            created_at,
            updated_at
        FROM revenues
        WHERE id = $1
        """,
        revenue_id,
    )

    if not current:
        raise HTTPException(status_code=404, detail="revenue not found")

    new_category = payload.category if payload.category is not None else current["category"]
    new_amount = payload.amount if payload.amount is not None else current["amount"]
    new_currency = payload.currency if payload.currency is not None else current["currency"]
    new_frequency = payload.frequency if payload.frequency is not None else current["frequency"]
    new_time_range = payload.time_range if payload.time_range is not None else current["time_range"]

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE revenues
            SET
                category   = $1,
                amount     = $2,
                currency   = $3,
                frequency  = $4,
                time_range = $5,
                updated_at = now()
            WHERE id = $6
            RETURNING
                id,
                plan_id,
                category,
                amount,
                currency,
                frequency,
                time_range,
                created_at,
                updated_at
            """,
            new_category,
            new_amount,
            new_currency,
            new_frequency,
            new_time_range,
            revenue_id,
        )

    return {
        "id": row["id"],
        "plan_id": row["plan_id"],
        "category": row["category"],
        "amount": row["amount"],
        "currency": row["currency"],
        "frequency": row["frequency"],
        "time_range": row["time_range"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.delete("/revenues/{revenue_id}", status_code=204)
async def delete_revenue(
    revenue_id: int,
    conn=Depends(get_db_connection),
):
    async with conn.transaction():
        result = await conn.execute(
            """
            DELETE FROM revenues
            WHERE id = $1
            """,
            revenue_id,
        )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="revenue not found")

    return Response(status_code=204)


# ==========================
# Plan 하위: Expenses
# ==========================

@router.post("/{plan_id}/expenses", response_model=ExpenseOut)
async def create_expense(
    plan_id: int,
    payload: ExpenseCreate,
    conn=Depends(get_db_connection),
):
    category = payload.category
    amount = payload.amount
    currency = payload.currency
    frequency = payload.frequency
    time_range = payload.time_range

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO expenses
                (plan_id, category, amount, currency, frequency, time_range)
            VALUES
                ($1,      $2,       $3,     $4,       $5,        $6)
            RETURNING
                id,
                plan_id,
                category,
                amount,
                currency,
                frequency,
                time_range,
                created_at,
                updated_at
            """,
            plan_id,
            category,
            amount,
            currency,
            frequency,
            time_range,
        )

    return {
        "id": row["id"],
        "plan_id": row["plan_id"],
        "category": row["category"],
        "amount": row["amount"],
        "currency": row["currency"],
        "frequency": row["frequency"],
        "time_range": row["time_range"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("/{plan_id}/expenses", response_model=list[ExpenseOut])
async def list_expenses(
    plan_id: int,
    conn=Depends(get_db_connection),
):
    rows = await conn.fetch(
        """
        SELECT
            id,
            plan_id,
            category,
            amount,
            currency,
            frequency,
            time_range,
            created_at,
            updated_at
        FROM expenses
        WHERE plan_id = $1
        ORDER BY created_at DESC
        """,
        plan_id,
    )

    return [
        {
            "id": row["id"],
            "plan_id": row["plan_id"],
            "category": row["category"],
            "amount": row["amount"],
            "currency": row["currency"],
            "frequency": row["frequency"],
            "time_range": row["time_range"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
async def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    conn=Depends(get_db_connection),
):
    current = await conn.fetchrow(
        """
        SELECT
            id,
            plan_id,
            category,
            amount,
            currency,
            frequency,
            time_range,
            created_at,
            updated_at
        FROM expenses
        WHERE id = $1
        """,
        expense_id,
    )

    if not current:
        raise HTTPException(status_code=404, detail="expense not found")

    new_category = payload.category if payload.category is not None else current["category"]
    new_amount = payload.amount if payload.amount is not None else current["amount"]
    new_currency = payload.currency if payload.currency is not None else current["currency"]
    new_frequency = payload.frequency if payload.frequency is not None else current["frequency"]
    new_time_range = payload.time_range if payload.time_range is not None else current["time_range"]

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE expenses
            SET
                category   = $1,
                amount     = $2,
                currency   = $3,
                frequency  = $4,
                time_range = $5,
                updated_at = now()
            WHERE id = $6
            RETURNING
                id,
                plan_id,
                category,
                amount,
                currency,
                frequency,
                time_range,
                created_at,
                updated_at
            """,
            new_category,
            new_amount,
            new_currency,
            new_frequency,
            new_time_range,
            expense_id,
        )

    return {
        "id": row["id"],
        "plan_id": row["plan_id"],
        "category": row["category"],
        "amount": row["amount"],
        "currency": row["currency"],
        "frequency": row["frequency"],
        "time_range": row["time_range"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.delete("/expenses/{expense_id}", status_code=204)
async def delete_expense(
    expense_id: int,
    conn=Depends(get_db_connection),
):
    async with conn.transaction():
        result = await conn.execute(
            """
            DELETE FROM expenses
            WHERE id = $1
            """,
            expense_id,
        )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="expense not found")

    return Response(status_code=204)


# ==========================
# Plan 하위: Taxes
# ==========================

@router.post("/{plan_id}/taxes", response_model=TaxOut)
async def create_tax(
    plan_id: int,
    payload: TaxCreate,
    conn=Depends(get_db_connection),
):
    category = payload.category

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO taxes
                (plan_id, category)
            VALUES
                ($1,      $2)
            RETURNING
                id,
                plan_id,
                category,
                created_at,
                updated_at
            """,
            plan_id,
            category,
        )

    return {
        "id": row["id"],
        "plan_id": row["plan_id"],
        "category": row["category"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("/{plan_id}/taxes", response_model=list[TaxOut])
async def list_taxes(
    plan_id: int,
    conn=Depends(get_db_connection),
):
    rows = await conn.fetch(
        """
        SELECT
            id,
            plan_id,
            category,
            created_at,
            updated_at
        FROM taxes
        WHERE plan_id = $1
        ORDER BY created_at DESC
        """,
        plan_id,
    )

    return [
        {
            "id": row["id"],
            "plan_id": row["plan_id"],
            "category": row["category"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


@router.patch("/taxes/{tax_id}", response_model=TaxOut)
async def update_tax(
    tax_id: int,
    payload: TaxUpdate,
    conn=Depends(get_db_connection),
):
    current = await conn.fetchrow(
        """
        SELECT
            id,
            plan_id,
            category,
            created_at,
            updated_at
        FROM taxes
        WHERE id = $1
        """,
        tax_id,
    )

    if not current:
        raise HTTPException(status_code=404, detail="tax not found")

    new_category = payload.category if payload.category is not None else current["category"]

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE taxes
            SET
                category   = $1,
                updated_at = now()
            WHERE id = $2
            RETURNING
                id,
                plan_id,
                category,
                created_at,
                updated_at
            """,
            new_category,
            tax_id,
        )

    return {
        "id": row["id"],
        "plan_id": row["plan_id"],
        "category": row["category"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.delete("/taxes/{tax_id}", status_code=204)
async def delete_tax(
    tax_id: int,
    conn=Depends(get_db_connection),
):
    async with conn.transaction():
        result = await conn.execute(
            """
            DELETE FROM taxes
            WHERE id = $1
            """,
            tax_id,
        )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="tax not found")

    return Response(status_code=204)
