from fastapi import APIRouter, Depends, HTTPException
import asyncpg

from app.db import get_db_connection
from app.schemas import AssetCreate, AssetUpdate, AssetOut
from app.auth import get_current_user, CurrentUser  # 가정

router = APIRouter(prefix="/assets", tags=["assets"])


# ========= 목록 조회 (내 assets만) =========
@router.get("/", response_model=list[AssetOut])
async def list_assets(
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    rows = await conn.fetch(
        """
        SELECT
            id, user_id,
            category::text AS category,
            has_loan,
            interest_rate, yield_rate,
            purchase_amount, purchase_ccy::text AS purchase_ccy,
            current_amount,  current_ccy::text  AS current_ccy,
            loan_amount,     loan_ccy::text     AS loan_ccy,
            repay_amount,    repay_ccy::text    AS repay_ccy,
            created_at, updated_at
        FROM assets
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
            "has_loan": r["has_loan"],
            "interest_rate": f(r["interest_rate"]),
            "yield_rate": f(r["yield_rate"]),
            "purchase_amount": f(r["purchase_amount"]),
            "purchase_ccy": r["purchase_ccy"],
            "current_amount": f(r["current_amount"]),
            "current_ccy": r["current_ccy"],
            "loan_amount": f(r["loan_amount"]),
            "loan_ccy": r["loan_ccy"],
            "repay_amount": f(r["repay_amount"]),
            "repay_ccy": r["repay_ccy"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


# ========= 생성 =========
@router.post("/", response_model=AssetOut)
async def insert_asset(
    payload: AssetCreate,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    if payload.category is None:
        raise HTTPException(status_code=400, detail="category is required")

    category = payload.category

    def up(v):
        return v.upper() if isinstance(v, str) else v

    has_loan        = payload.has_loan
    interest_rate   = payload.interest_rate
    yield_rate      = payload.yield_rate
    purchase_amount = payload.purchase_amount
    purchase_ccy    = up(payload.purchase_ccy)
    current_amount  = payload.current_amount
    current_ccy     = up(payload.current_ccy)
    loan_amount     = payload.loan_amount
    loan_ccy        = up(payload.loan_ccy)
    repay_amount    = payload.repay_amount
    repay_ccy       = up(payload.repay_ccy)

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO assets
                (user_id, category, has_loan, interest_rate, yield_rate,
                 purchase_amount, purchase_ccy, current_amount, current_ccy,
                 loan_amount, loan_ccy, repay_amount, repay_ccy)
            VALUES
                ($1, $2, $3, $4, $5,
                 $6, $7, $8, $9,
                 $10, $11, $12, $13)
            RETURNING
                id, user_id, category::text AS category, has_loan,
                interest_rate, yield_rate,
                purchase_amount, purchase_ccy::text AS purchase_ccy,
                current_amount,  current_ccy::text  AS current_ccy,
                loan_amount,     loan_ccy::text     AS loan_ccy,
                repay_amount,    repay_ccy::text    AS repay_ccy,
                created_at, updated_at
            """,
            current_user.id,
            category,
            has_loan,
            interest_rate,
            yield_rate,
            purchase_amount,
            purchase_ccy,
            current_amount,
            current_ccy,
            loan_amount,
            loan_ccy,
            repay_amount,
            repay_ccy,
        )

    def f(v): return float(v) if v is not None else None

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "category": row["category"],
        "has_loan": row["has_loan"],
        "interest_rate": f(row["interest_rate"]),
        "yield_rate": f(row["yield_rate"]),
        "purchase_amount": f(row["purchase_amount"]),
        "purchase_ccy": row["purchase_ccy"],
        "current_amount": f(row["current_amount"]),
        "current_ccy": row["current_ccy"],
        "loan_amount": f(row["loan_amount"]),
        "loan_ccy": row["loan_ccy"],
        "repay_amount": f(row["repay_amount"]),
        "repay_ccy": row["repay_ccy"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ========= 부분 수정 =========
@router.patch("/{asset_id}", response_model=AssetOut)
async def update_asset(
    asset_id: int,
    payload: AssetUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    mapping = {
        "category": "category",
        "has_loan": "has_loan",
        "interest_rate": "interest_rate",
        "yield_rate": "yield_rate",
        "purchase_amount": "purchase_amount",
        "purchase_ccy": "purchase_ccy",
        "current_amount": "current_amount",
        "current_ccy": "current_ccy",
        "loan_amount": "loan_amount",
        "loan_ccy": "loan_ccy",
        "repay_amount": "repay_amount",
        "repay_ccy": "repay_ccy",
    }

    data = payload.model_dump(exclude_unset=True)

    fields, vals = [], []
    for k, v in data.items():
        if k in mapping:
            if k in {"category", "purchase_ccy", "current_ccy", "loan_ccy", "repay_ccy"} and v is not None:
                v = str(v).upper()
            fields.append(f'{mapping[k]} = ${len(vals)+1}')
            vals.append(v)

    if not fields:
        raise HTTPException(400, "no updatable fields")

    # user_id, asset_id 조건
    vals.extend([current_user.id, asset_id])

    q = f"""
        UPDATE assets
           SET {', '.join(fields)}, updated_at = now()
         WHERE user_id = ${len(vals)-1} AND id = ${len(vals)}
        RETURNING
            id, user_id, category::text AS category, has_loan,
            interest_rate, yield_rate,
            purchase_amount, purchase_ccy::text AS purchase_ccy,
            current_amount,  current_ccy::text  AS current_ccy,
            loan_amount,     loan_ccy::text     AS loan_ccy,
            repay_amount,    repay_ccy::text    AS repay_ccy,
            created_at, updated_at
    """

    row = await conn.fetchrow(q, *vals)
    if not row:
        raise HTTPException(404, "asset not found")

    def f(v): return float(v) if v is not None else None

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "category": row["category"],
        "has_loan": row["has_loan"],
        "interest_rate": f(row["interest_rate"]),
        "yield_rate": f(row["yield_rate"]),
        "purchase_amount": f(row["purchase_amount"]),
        "purchase_ccy": row["purchase_ccy"],
        "current_amount": f(row["current_amount"]),
        "current_ccy": row["current_ccy"],
        "loan_amount": f(row["loan_amount"]),
        "loan_ccy": row["loan_ccy"],
        "repay_amount": f(row["repay_amount"]),
        "repay_ccy": row["repay_ccy"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ========= 삭제 =========
@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    res = await conn.execute(
        "DELETE FROM assets WHERE user_id=$1 AND id=$2",
        current_user.id,
        asset_id,
    )
    if not res.endswith(" 1"):
        raise HTTPException(404, "asset not found")
    return {"status": "ok", "deleted_id": asset_id}
