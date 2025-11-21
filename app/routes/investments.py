from fastapi import APIRouter, Depends, HTTPException
import asyncpg

from app.db import get_db_connection
from app.schemas import InvestmentCreate, InvestmentUpdate, InvestmentOut
from app.auth import get_current_user, CurrentUser  # 가정

router = APIRouter(prefix="/investments", tags=["investments"])


# ===== 목록 조회 (내 investments만) =====
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
            name,
            amount,
            yield_rate,
            currency::text AS currency,
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
            "id": r["id"],
            "user_id": r["user_id"],
            "category": r["category"],
            "name": r["name"],
            "amount": float(r["amount"]) if r["amount"] is not None else 0.0,
            "yield_rate": float(r["yield_rate"]) if r["yield_rate"] is not None else None,
            "currency": r["currency"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
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

    category   = payload.category
    currency   = payload.currency
    name       = payload.name
    amount     = payload.amount
    yield_rate = payload.yield_rate

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO investments
                (user_id, category, name, amount, yield_rate, currency)
            VALUES
                ($1,      $2,       $3,   COALESCE($4,0), $5,        $6)
            RETURNING
                id,
                user_id,
                category::text AS category,
                name,
                amount,
                yield_rate,
                currency::text AS currency,
                created_at,
                updated_at
            """,
            current_user.id,
            category,
            name,
            amount,
            yield_rate,
            currency,
        )

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "category": row["category"],
        "name": row["name"],
        "amount": float(row["amount"]) if row["amount"] is not None else 0.0,
        "yield_rate": float(row["yield_rate"]) if row["yield_rate"] is not None else None,
        "currency": row["currency"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ===== 부분 수정 (PATCH) =====
@router.patch("/{investment_id}", response_model=InvestmentOut)
async def update_investment(
    investment_id: int,
    payload: InvestmentUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    # Pydantic v2 기준: model_dump(exclude_unset=True)
    data = payload.model_dump(exclude_unset=True)

    fields = []
    vals: list = []

    mapping = {
        "category": "category",
        "name": "name",
        "amount": "amount",
        "yield_rate": "yield_rate",
        "currency": "currency",
    }

    for k, v in data.items():
        if k in mapping:
            if k in {"category", "currency"} and v is not None:
                v = str(v).upper()
            fields.append(f'{mapping[k]} = ${len(vals) + 1}')
            vals.append(v)

    if not fields:
        raise HTTPException(400, "no updatable fields")

    # user_id, investment_id 조건 붙이기
    vals.extend([current_user.id, investment_id])

    q = f"""
        UPDATE investments
           SET {', '.join(fields)}, updated_at = now()
         WHERE user_id = ${len(vals)-1} AND id = ${len(vals)}
        RETURNING
            id,
            user_id,
            category::text AS category,
            name,
            amount,
            yield_rate,
            currency::text AS currency,
            created_at,
            updated_at
    """

    row = await conn.fetchrow(q, *vals)
    if not row:
        raise HTTPException(404, "investment not found")

    return {
        **dict(row),
        "amount": float(row["amount"]) if row["amount"] is not None else 0.0,
        "yield_rate": float(row["yield_rate"]) if row["yield_rate"] is not None else None,
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
