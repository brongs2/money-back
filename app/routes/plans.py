# app/api/routes/plans.py

from fastapi import APIRouter, Depends, HTTPException, Query, Body, Response
from sqlalchemy.orm import Session
import asyncpg
from app.db import get_db_connection
from app.schemas import (
    PlanCreate, PlanOut, PlanUpdate,
    RevenueCreate, RevenueOut, RevenueUpdate,
    TaxCreate, TaxOut, TaxUpdate,
)

router = APIRouter(prefix="/plans", tags=["plans"])


# ----- Plan 기본 CRUD -----
@router.post("/", response_model=PlanOut)
async def create_plan(
    payload: PlanCreate,
    user_id: int,  # 보통은 토큰에서 꺼내거나 path/query로 받음
    conn: Session = Depends(get_db_connection),
):
    title = payload.title
    description = payload.description
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO plans
                (user_id, title, description)
            VALUES
                ($1,      $2, $3)
            RETURNING
                id, user_id,
                title,
                description,

                created_at, updated_at
            """,
            user_id, title, description
        )

    # 숫자/NULL 정리해서 반환
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "description": row["description"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
# ----- Plan 목록 조회 -----
@router.get("/", response_model=list[PlanOut])
async def list_plans(
    user_id: int,
    conn = Depends(get_db_connection),
):
    rows = await conn.fetch(
        """
        SELECT
            id,
            user_id,
            title,
            description,
            created_at,
            updated_at
        FROM plans
        WHERE user_id = $1
        ORDER BY created_at DESC
        """,
        user_id,
    )

    return [
        {
            "id": row["id"],
            "user_id": row["user_id"],
            "title": row["title"],
            "description": row["description"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


# ----- Plan 수정 -----
@router.patch("/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: int,
    payload: PlanUpdate,
    user_id: int,
    conn = Depends(get_db_connection),
):
    # 기존 데이터 조회 (user_id까지 같이 확인해서 본인 것만 수정 가능)
    current = await conn.fetchrow(
        """
        SELECT
            id,
            user_id,
            title,
            description,
            created_at,
            updated_at
        FROM plans
        WHERE id = $1 AND user_id = $2
        """,
        plan_id,
        user_id,
    )

    if not current:
        raise HTTPException(status_code=404, detail="plan not found")

    # 부분 업데이트 처리 (PATCH)
    new_title = payload.title if payload.title is not None else current["title"]
    new_description = (
        payload.description
        if payload.description is not None
        else current["description"]
    )

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE plans
            SET
                title       = $1,
                description = $2,
                updated_at  = now()
            WHERE id = $3 AND user_id = $4
            RETURNING
                id,
                user_id,
                title,
                description,
                created_at,
                updated_at
            """,
            new_title,
            new_description,
            plan_id,
            user_id,
        )

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "description": row["description"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ----- Plan 삭제 -----
@router.delete("/{plan_id}", status_code=204)
async def delete_plan(
    plan_id: int,
    user_id: int,
    conn = Depends(get_db_connection),
):
    async with conn.transaction():
        result = await conn.execute(
            """
            DELETE FROM plans
            WHERE id = $1 AND user_id = $2
            """,
            plan_id,
            user_id,
        )

    # asyncpg.execute() 는 "DELETE 0" / "DELETE 1" 같은 문자열 반환
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="plan not found")

    # 204 No Content
    return Response(status_code=204)


@router.post("/{plan_id}/revenues", response_model=RevenueOut)
async def create_revenue(
    plan_id: int,
    payload: RevenueCreate,
    conn = Depends(get_db_connection),
):
    # payload.plan_id 대신 path 로 받은 plan_id 우선 사용
    category   = payload.category
    amount     = payload.amount
    currency   = payload.currency
    frequency  = payload.frequency
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
    conn = Depends(get_db_connection),
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
    conn = Depends(get_db_connection),
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

    new_category   = payload.category   if payload.category   is not None else current["category"]
    new_amount     = payload.amount     if payload.amount     is not None else current["amount"]
    new_currency   = payload.currency   if payload.currency   is not None else current["currency"]
    new_frequency  = payload.frequency  if payload.frequency  is not None else current["frequency"]
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
    conn = Depends(get_db_connection),
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
# Plan 하위: Taxes
# ==========================

@router.post("/{plan_id}/taxes", response_model=TaxOut)
async def create_tax(
    plan_id: int,
    payload: TaxCreate,
    conn = Depends(get_db_connection),
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
    conn = Depends(get_db_connection),
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
    conn = Depends(get_db_connection),
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
    conn = Depends(get_db_connection),
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