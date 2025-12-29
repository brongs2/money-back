from fastapi import APIRouter, Depends, HTTPException
import asyncpg
from datetime import date
from app.db import get_db_connection
from app.schemas.schemas import InvestmentCreate, InvestmentUpdate, InvestmentOut
from app.auth import get_current_user, CurrentUser

router = APIRouter(prefix="/investments", tags=["investments"])

# ===== 목록 조회 =====
@router.get("/", response_model=list[InvestmentOut])
async def list_investments(
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    rows = await conn.fetch(
        """
        SELECT
            id,
            user_id,
            category::text AS category,
            amount,
            roi,
            dividend,
            deposit,                         -- ✅ 추가
            deposit_frequency::text AS deposit_frequency, -- ✅ 추가
            maturity_date,                   -- ✅ 추가
            created_at,
            updated_at
        FROM investments
        WHERE user_id = $1
        ORDER BY created_at DESC NULLS LAST, id DESC
        """,
        current_user.id,
    )

    return [
        {
            **dict(r),
            "amount": float(r["amount"]) if r["amount"] is not None else 0.0,
            "roi": float(r["roi"]) if r["roi"] is not None else None,
            "dividend": float(r["dividend"]) if r["dividend"] is not None else None,
            "deposit": float(r["deposit"]) if r["deposit"] is not None else 0.0,
            "deposit_frequency": r["deposit_frequency"],
            "maturity_date": r["maturity_date"],
        }
        for r in rows
    ]


# ===== 생성 =====
@router.post("/", response_model=InvestmentOut)
async def insert_investment(
    payload: InvestmentCreate,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    if payload.category is None:
        raise HTTPException(400, "category is required")

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO investments
                (user_id, category, amount, roi, dividend, 
                 deposit, deposit_frequency, maturity_date) -- ✅ currency 제외, 필드 추가
            VALUES
                ($1, $2, $3, COALESCE($4, 0), COALESCE($5, 0), $6, $7, $8)
            RETURNING
                id,
                user_id,
                category::text AS category,
                amount,
                roi,
                dividend,
                deposit,
                deposit_frequency::text AS deposit_frequency,
                maturity_date,
                created_at,
                updated_at
            """,
            current_user.id,
            payload.category.upper(),
            payload.amount,
            payload.roi,
            payload.dividend,
            payload.deposit,
            payload.deposit_frequency.upper() if payload.deposit_frequency else None,
            payload.maturity_date,
        )

    return {
        **dict(row),
        "amount": float(row["amount"]),
        "roi": float(row["roi"]),
        "dividend": float(row["dividend"]),
        "deposit": float(row["deposit"]),
    }


# ===== 부분 수정 (PATCH) =====
@router.patch("/{investment_id}", response_model=InvestmentOut)
async def update_investment(
    investment_id: int,
    payload: InvestmentUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    data = payload.model_dump(exclude_unset=True)

    fields = []
    vals = []

    # mapping에서 currency 제거, 새 필드 추가
    mapping = {
        "category": "category",
        "amount": "amount",
        "roi": "roi",
        "dividend": "dividend",
        "deposit": "deposit",
        "deposit_frequency": "deposit_frequency",
        "maturity_date": "maturity_date",
    }

    for k, v in data.items():
        if k in mapping:
            if k in {"category", "deposit_frequency"} and v is not None:
                v = str(v).upper()
            fields.append(f'{mapping[k]} = ${len(vals) + 1}')
            vals.append(v)

    if not fields:
        raise HTTPException(400, "no updatable fields")

    vals.extend([current_user.id, investment_id])

    q = f"""
        UPDATE investments
           SET {', '.join(fields)}, updated_at = now()
         WHERE user_id = ${len(vals)-1} AND id = ${len(vals)}
        RETURNING
            id,
            user_id,
            category::text AS category,
            amount,
            roi,
            dividend,
            deposit,
            deposit_frequency::text AS deposit_frequency,
            maturity_date,
            created_at,
            updated_at
    """

    row = await conn.fetchrow(q, *vals)
    if not row:
        raise HTTPException(404, "investment not found")

    return {
        **dict(row),
        "amount": float(row["amount"]),
        "roi": float(row["roi"]),
        "dividend": float(row["dividend"]),
        "deposit": float(row["deposit"]),
    }

# ===== 삭제 =====
@router.delete("/{investment_id}")
async def delete_investment(
    investment_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    res = await conn.execute(
        "DELETE FROM investments WHERE user_id=$1 AND id=$2",
        current_user.id,
        investment_id,
    )  # 예: "DELETE 1"

    if not res.endswith(" 1"):
        raise HTTPException(404, "investment not found")

    return {"status": "ok", "deleted_id": investment_id}
