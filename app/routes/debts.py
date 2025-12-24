from fastapi import APIRouter, Depends, HTTPException
import asyncpg

from app.db import get_db_connection
from app.schemas.schemas import DebtCreate, DebtUpdate, DebtOut
from app.auth import get_current_user, CurrentUser  # 가정

router = APIRouter(prefix="/debts", tags=["debts"])


# ========= 목록 조회 (내 debts만) =========
@router.get("/", response_model=list[DebtOut])
async def list_debts(
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    rows = await conn.fetch(
        """
        SELECT
            id, user_id,
            category::text AS category,
            loan_amount, loan_ccy::text AS loan_ccy,
            repay_amount, repay_ccy::text AS repay_ccy,
            interest_rate,
            compound::text AS compound,
            currency::text AS currency,
            created_at, updated_at
        FROM debts
        WHERE user_id = $1
        ORDER BY created_at DESC NULLS LAST, id DESC
        """,
        current_user.id,
    )

    def f(v): return float(v) if v is not None else None

    return [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "category": r["category"],
            "loan_amount": f(r["loan_amount"]),
            "loan_ccy": r["loan_ccy"],
            "repay_amount": f(r["repay_amount"]),
            "repay_ccy": r["repay_ccy"],
            "interest_rate": f(r["interest_rate"]),
            "compound": r["compound"],
            "currency": r["currency"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


# ========= 생성 =========
@router.post("/", response_model=DebtOut)
async def insert_debt(
    payload: DebtCreate,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    # 필수값 체크
    required = ["category", "loan_amount", "repay_amount", "interest_rate"]
    missing = [k for k in required if getattr(payload, k, None) is None]

    if missing:
        raise HTTPException(status_code=400, detail=f"required fields: {', '.join(missing)}")

    category     = payload.category
    compound     = payload.compound
    currency     = payload.currency
    loan_ccy     = payload.loan_ccy
    repay_ccy    = payload.repay_ccy
    loan_amount  = payload.loan_amount
    repay_amount = payload.repay_amount
    interest_rate = payload.interest_rate

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO debts
                (user_id, category,
                 loan_amount, loan_ccy,
                 repay_amount, repay_ccy,
                 interest_rate, compound, currency)
            VALUES
                ($1, $2,
                 $3, $4,
                 $5, $6,
                 $7, $8, $9)
            RETURNING
                id, user_id,
                category::text AS category,
                loan_amount, loan_ccy::text AS loan_ccy,
                repay_amount, repay_ccy::text AS repay_ccy,
                interest_rate,
                compound::text AS compound,
                currency::text AS currency,
                created_at, updated_at
            """,
            current_user.id,
            category,
            loan_amount, loan_ccy,
            repay_amount, repay_ccy,
            interest_rate, compound, currency,
        )

    def f(v): return float(v) if v is not None else None

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "category": row["category"],
        "loan_amount": f(row["loan_amount"]),
        "loan_ccy": row["loan_ccy"],
        "repay_amount": f(row["repay_amount"]),
        "repay_ccy": row["repay_ccy"],
        "interest_rate": f(row["interest_rate"]),
        "compound": row["compound"],
        "currency": row["currency"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ========= 부분 수정 =========
@router.patch("/{debt_id}", response_model=DebtOut)
async def update_debt(
    debt_id: int,
    payload: DebtUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    mapping = {
        "category": "category",
        "loan_amount": "loan_amount",
        "loan_ccy": "loan_ccy",
        "repay_amount": "repay_amount",
        "repay_ccy": "repay_ccy",
        "interest_rate": "interest_rate",
        "compound": "compound",
        "currency": "currency",
    }

    data = payload.model_dump(exclude_unset=True)

    fields, vals = [], []
    for k, v in data.items():
        if k in mapping:
            if k in {"category", "loan_ccy", "repay_ccy", "compound", "currency"} and v is not None:
                v = str(v).upper()
            fields.append(f'{mapping[k]} = ${len(vals)+1}')
            vals.append(v)

    if not fields:
        raise HTTPException(status_code=400, detail="no updatable fields")

    vals.extend([current_user.id, debt_id])

    q = f"""
        UPDATE debts
           SET {', '.join(fields)}, updated_at = now()
         WHERE user_id = ${len(vals)-1} AND id = ${len(vals)}
        RETURNING
            id, user_id,
            category::text AS category,
            loan_amount, loan_ccy::text AS loan_ccy,
            repay_amount, repay_ccy::text AS repay_ccy,
            interest_rate,
            compound::text AS compound,
            currency::text AS currency,
            created_at, updated_at
    """
    row = await conn.fetchrow(q, *vals)
    if not row:
        raise HTTPException(status_code=404, detail="debt not found")

    def f(v): return float(v) if v is not None else None

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "category": row["category"],
        "loan_amount": f(row["loan_amount"]),
        "loan_ccy": row["loan_ccy"],
        "repay_amount": f(row["repay_amount"]),
        "repay_ccy": row["repay_ccy"],
        "interest_rate": f(row["interest_rate"]),
        "compound": row["compound"],
        "currency": row["currency"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ========= 삭제 =========
@router.delete("/{debt_id}")
async def delete_debt(
    debt_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    res = await conn.execute(
        "DELETE FROM debts WHERE user_id=$1 AND id=$2",
        current_user.id,
        debt_id,
    )
    if not res.endswith(" 1"):
        raise HTTPException(status_code=404, detail="debt not found")
    return {"status": "ok", "deleted_id": debt_id}
