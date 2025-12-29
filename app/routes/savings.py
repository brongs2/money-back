from fastapi import APIRouter, Depends, HTTPException
import asyncpg
from datetime import date
from typing import Optional

from app.db import get_db_connection
from app.schemas.schemas import SavingCreate, SavingUpdate, SavingOut
from app.auth import get_current_user, CurrentUser

router = APIRouter(prefix="/savings", tags=["savings"])

# ===== 목록 조회 =====
@router.get("/", response_model=list[SavingOut])
async def list_savings(
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
            interest_rate,
            compound::text AS compound,
            deposit,
            deposit_frequency::text AS deposit_frequency,
            maturity_date,
            created_at,
            updated_at
        FROM savings
        WHERE user_id = $1
        ORDER BY created_at DESC NULLS LAST, id DESC
        """,
        current_user.id,
    )

    return [
        {
            **dict(r),
            "category": r["category"],
            "amount": float(r["amount"]) if r["amount"] is not None else 0.0,
            "interest_rate": float(r["interest_rate"]) if r["interest_rate"] is not None else None,
            "deposit": float(r["deposit"]) if r["deposit"] is not None else 0.0,
            "deposit_frequency": r["deposit_frequency"],
            "maturity_date": r["maturity_date"],
        }
        for r in rows
    ]


# ===== 생성 =====
@router.post("/", response_model=SavingOut)
async def insert_saving(
    payload: SavingCreate,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    if payload.category is None:
        raise HTTPException(status_code=400, detail="category is required")

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO savings
                (user_id, category, amount, interest_rate, compound, 
                 deposit, deposit_frequency, maturity_date)
            VALUES
                ($1, $2, $3, COALESCE($4, 0), $5, $6, $7, $8)
            RETURNING
                id,
                user_id,
                category::text AS category,
                amount,
                interest_rate,
                compound::text AS compound,
                deposit,
                deposit_frequency::text AS deposit_frequency,
                maturity_date,
                created_at,
                updated_at
            """,
            current_user.id,
            payload.category.upper(),
            payload.amount,
            payload.interest_rate,
            payload.compound.upper() if payload.compound else 'COMPOUND',
            payload.deposit,
            payload.deposit_frequency.upper() if payload.deposit_frequency else None,
            payload.maturity_date
        )

    return {
        **dict(row),
        "amount": float(row["amount"]),
        "interest_rate": float(row["interest_rate"]) if row["interest_rate"] is not None else None,
        "deposit": float(row["deposit"]) if row["deposit"] is not None else 0.0,
    }


# ===== 부분 수정 (PATCH) =====
@router.patch("/{saving_id}", response_model=SavingOut)
async def update_saving(
    saving_id: int,
    payload: SavingUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    data = payload.model_dump(exclude_unset=True)

    fields = []
    vals = []

    # mapping에서 currency 제거
    mapping = {
        "category": "category",
        "amount": "amount",
        "interest_rate": "interest_rate",
        "compound": "compound", 
        "deposit": "deposit",
        "deposit_frequency": "deposit_frequency",
        "maturity_date": "maturity_date",
    }

    for k, v in data.items():
        if k in mapping:
            # ENUM 값들은 대문자로 통일
            if k in {"category", "compound", "deposit_frequency"} and v is not None:
                v = str(v).upper()
            fields.append(f'{mapping[k]} = ${len(vals) + 1}')
            vals.append(v)

    if not fields:
        raise HTTPException(status_code=400, detail="no updatable fields")

    vals.extend([current_user.id, saving_id])

    q = f"""
        UPDATE savings
           SET {', '.join(fields)}, updated_at = now()
         WHERE user_id = ${len(vals)-1} AND id = ${len(vals)}
        RETURNING
            id,
            user_id,
            category::text AS category,
            amount,
            interest_rate,
            compound::text AS compound,
            deposit,
            deposit_frequency::text AS deposit_frequency,
            maturity_date,
            created_at,
            updated_at
    """
    row = await conn.fetchrow(q, *vals)
    if not row:
        raise HTTPException(status_code=404, detail="saving not found")

    return {
        **dict(row),
        "amount": float(row["amount"]),
        "interest_rate": float(row["interest_rate"]) if row["interest_rate"] is not None else None,
        "deposit": float(row["deposit"]) if row["deposit"] is not None else 0.0,
    }

# (삭제 로직은 기존과 동일하므로 유지)
# ===== 삭제 =====
@router.delete("/{saving_id}")
async def delete_saving(
    saving_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    res = await conn.execute(
        "DELETE FROM savings WHERE user_id=$1 AND id=$2",
        current_user.id,
        saving_id,
    )  # 예: "DELETE 1"

    if not res.endswith(" 1"):
        raise HTTPException(status_code=404, detail="saving not found")

    return {"status": "ok", "deleted_id": saving_id}
