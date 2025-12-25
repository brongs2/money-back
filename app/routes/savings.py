from fastapi import APIRouter, Depends, HTTPException
import asyncpg

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
            compound::text AS compound,  -- ✅ 추가
            currency::text AS currency,
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
            "id": r["id"],
            "user_id": r["user_id"],
            "category": r["category"],
            "amount": float(r["amount"]) if r["amount"] is not None else 0.0,
            "interest_rate": float(r["interest_rate"]) if r["interest_rate"] is not None else None,
            "compound": r["compound"],  
            "currency": r["currency"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
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
                (user_id, category, amount, interest_rate, currency, compound)
            VALUES
                ($1, $2, $3, COALESCE($4, 0), $5, $6) -- ✅ $6 추가
            RETURNING
                id,
                user_id,
                category::text AS category,
                amount,
                interest_rate,
                compound::text AS compound, -- ✅ 추가
                currency::text AS currency,
                created_at,
                updated_at
            """,
            current_user.id,
            payload.category,
            payload.amount,
            payload.interest_rate,
            payload.currency,
            payload.compound or 'COMPOUND' # ✅ 값이 없으면 기본값 적용
        )

    return {
        **dict(row),
        "amount": float(row["amount"]),
        "interest_rate": float(row["interest_rate"]) if row["interest_rate"] is not None else None,
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

    # ✅ mapping에 compound 추가
    mapping = {
        "category": "category",
        "amount": "amount",
        "interest_rate": "interest_rate",
        "currency": "currency",
        "compound": "compound", 
    }

    for k, v in data.items():
        if k in mapping:
            # ENUM 값들은 대문자로 통일
            if k in {"category", "currency", "compound"} and v is not None:
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
            compound::text AS compound, -- ✅ 추가
            currency::text AS currency,
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
    }
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
