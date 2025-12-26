from fastapi import APIRouter, Depends, HTTPException
import asyncpg
from typing import Optional

from app.db import get_db_connection
from app.schemas.schemas import AssetCreate, AssetUpdate, AssetOut
from app.auth import get_current_user, CurrentUser

router = APIRouter(prefix="/assets", tags=["assets"])

def f(v): return float(v) if v is not None else None

def validate_repayment(loan_amount, interest_rate, repay_amount):
    """상환액이 월 이자보다 큰지 검증하는 공통 로직"""
    loan_val = f(loan_amount) or 0
    if loan_val > 0:
        monthly_interest = (loan_val * (f(interest_rate) / 100)) / 12
        if f(repay_amount) < monthly_interest:
            raise HTTPException(
                status_code=400, 
                detail=f"상환액(₩{f(repay_amount):,.0f})이 월 이자(₩{monthly_interest:,.0f})보다 적어 부채가 무한히 증식합니다."
            )

async def get_assets_data(user_id: int, conn: asyncpg.Connection):
    return await conn.fetch(
        """
        SELECT id, user_id, category::text AS category,
               interest_rate, roi, dividend, amount, currency::text AS currency,
               loan_amount, repay_amount, created_at, updated_at
        FROM assets WHERE user_id = $1
        ORDER BY created_at DESC NULLS LAST, id DESC
        """, user_id
    )

@router.get("/", response_model=list[AssetOut])
async def list_assets(current_user: CurrentUser = Depends(get_current_user), conn: asyncpg.Connection = Depends(get_db_connection)):
    return await get_assets_data(current_user.id, conn)

@router.post("/", response_model=AssetOut)
async def insert_asset(payload: AssetCreate, current_user: CurrentUser = Depends(get_current_user), conn: asyncpg.Connection = Depends(get_db_connection)):
    if not payload.category:
        raise HTTPException(status_code=400, detail="category is required")

    # ✅ 검증 로직 실행
    validate_repayment(payload.loan_amount, payload.interest_rate, payload.repay_amount)

    def up(v): return v.upper() if isinstance(v, str) else v
    
    row = await conn.fetchrow(
        """
        INSERT INTO assets (user_id, category, interest_rate, roi, dividend, amount, currency, loan_amount, repay_amount)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id, user_id, category::text AS category, interest_rate, roi, dividend, amount, currency::text AS currency, loan_amount, repay_amount, created_at, updated_at
        """,
        current_user.id, up(payload.category), payload.interest_rate, payload.roi, payload.dividend, payload.amount, up(payload.currency), payload.loan_amount, payload.repay_amount
    )
    return row

@router.patch("/{asset_id}", response_model=AssetOut)
async def update_asset(asset_id: int, payload: AssetUpdate, current_user: CurrentUser = Depends(get_current_user), conn: asyncpg.Connection = Depends(get_db_connection)):
    existing = await conn.fetchrow("SELECT loan_amount, interest_rate, repay_amount FROM assets WHERE id = $1 AND user_id = $2", asset_id, current_user.id)
    if not existing:
        raise HTTPException(404, "asset not found")

    data = payload.model_dump(exclude_unset=True)
    
    # ✅ 기존 값과 새 값을 합쳐서 재검증
    new_loan = data.get("loan_amount", existing["loan_amount"])
    new_rate = data.get("interest_rate", existing["interest_rate"])
    new_repay = data.get("repay_amount", existing["repay_amount"])
    validate_repayment(new_loan, new_rate, new_repay)

    mapping = {"category": "category", "interest_rate": "interest_rate", "roi": "roi", "dividend": "dividend", "amount": "amount", "currency": "currency", "loan_amount": "loan_amount", "repay_amount": "repay_amount"}
    fields, vals = [], []
    for k, v in data.items():
        if k in mapping:
            if k in {"category", "currency"} and v is not None: v = str(v).upper()
            fields.append(f'{mapping[k]} = ${len(vals)+1}')
            vals.append(v)

    if not fields: raise HTTPException(400, "no updatable fields")
    vals.extend([current_user.id, asset_id])

    row = await conn.fetchrow(f"UPDATE assets SET {', '.join(fields)}, updated_at = now() WHERE user_id = ${len(vals)-1} AND id = ${len(vals)} RETURNING id, user_id, category::text AS category, interest_rate, roi, dividend, amount, currency::text AS currency, loan_amount, repay_amount, created_at, updated_at", *vals)
    return row

@router.delete("/{asset_id}")
async def delete_asset(asset_id: int, current_user: CurrentUser = Depends(get_current_user), conn: asyncpg.Connection = Depends(get_db_connection)):
    res = await conn.execute("DELETE FROM assets WHERE user_id=$1 AND id=$2", current_user.id, asset_id)
    if not res.endswith(" 1"): raise HTTPException(404, "asset not found")
    return {"status": "ok", "deleted_id": asset_id}