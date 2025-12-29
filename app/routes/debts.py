from fastapi import APIRouter, Depends, HTTPException
import asyncpg
from typing import Optional

from app.db import get_db_connection
from app.schemas.schemas import DebtCreate, DebtUpdate, DebtOut
from app.auth import get_current_user, CurrentUser

router = APIRouter(prefix="/debts", tags=["debts"])

def validate_debt_repayment(loan_amount, interest_rate, repay_amount):
    """부채 상환액 검증: 상환액이 월 이자보다 커야 원금이 줄어듦"""
    loan_val = float(loan_amount) if loan_amount is not None else 0.0
    if loan_val > 0:
        rate_val = float(interest_rate) if interest_rate is not None else 0.0
        repay_val = float(repay_amount) if repay_amount is not None else 0.0
        
        # 월 이자 계산
        monthly_interest = (loan_val * (rate_val / 100)) / 12
        if repay_val <= monthly_interest:
            raise HTTPException(
                status_code=400, 
                detail=f"월 상환액(₩{repay_val:,.0f})이 월 이자(₩{monthly_interest:,.0f})보다 크지 않으면 빚이 줄어들지 않습니다."
            )

async def get_debts_data(user_id: int, conn: asyncpg.Connection):
    """사용자의 부채 목록 조회 (currency 제외)"""
    rows = await conn.fetch(
        """
        SELECT id, user_id, category::text AS category,
               loan_amount, repay_amount, interest_rate, 
               compound::text AS compound, created_at, updated_at
        FROM debts 
        WHERE user_id = $1
        ORDER BY created_at DESC NULLS LAST, id DESC
        """, user_id
    )
    
    # asyncpg Record를 float이 포함된 dict로 변환
    return [
        {
            **dict(r),
            "loan_amount": float(r["loan_amount"]) if r["loan_amount"] is not None else 0.0,
            "repay_amount": float(r["repay_amount"]) if r["repay_amount"] is not None else 0.0,
            "interest_rate": float(r["interest_rate"]) if r["interest_rate"] is not None else 0.0,
        }
        for r in rows
    ]

# ========= 목록 조회 =========
@router.get("/", response_model=list[DebtOut])
async def list_debts(
    current_user: CurrentUser = Depends(get_current_user), 
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    return await get_debts_data(current_user.id, conn)

# ========= 생성 =========
@router.post("/", response_model=DebtOut)
async def insert_debt(
    payload: DebtCreate, 
    current_user: CurrentUser = Depends(get_current_user), 
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    # 상환 검증
    validate_debt_repayment(payload.loan_amount, payload.interest_rate, payload.repay_amount)

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO debts (user_id, category, loan_amount, repay_amount, interest_rate, compound)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, user_id, category::text AS category, 
                      loan_amount, repay_amount, interest_rate, 
                      compound::text AS compound, created_at, updated_at
            """,
            current_user.id, 
            payload.category.upper() if payload.category else None, 
            payload.loan_amount, 
            payload.repay_amount, 
            payload.interest_rate, 
            payload.compound.upper() if payload.compound else 'COMPOUND'
        )
    
    res = dict(row)
    res["loan_amount"] = float(res["loan_amount"])
    res["repay_amount"] = float(res["repay_amount"])
    res["interest_rate"] = float(res["interest_rate"])
    return res

# ========= 부분 수정 =========
@router.patch("/{debt_id}", response_model=DebtOut)
async def update_debt(
    debt_id: int, 
    payload: DebtUpdate, 
    current_user: CurrentUser = Depends(get_current_user), 
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    existing = await conn.fetchrow(
        "SELECT loan_amount, interest_rate, repay_amount FROM debts WHERE id = $1 AND user_id = $2", 
        debt_id, current_user.id
    )
    if not existing:
        raise HTTPException(404, "debt not found")

    data = payload.model_dump(exclude_unset=True)
    
    # 기존 값과 새 값 병합 후 재검증
    new_loan = data.get("loan_amount", existing["loan_amount"])
    new_rate = data.get("interest_rate", existing["interest_rate"])
    new_repay = data.get("repay_amount", existing["repay_amount"])
    validate_debt_repayment(new_loan, new_rate, new_repay)

    mapping = {
        "category": "category", 
        "loan_amount": "loan_amount", 
        "repay_amount": "repay_amount", 
        "interest_rate": "interest_rate", 
        "compound": "compound"
    }
    
    fields, vals = [], []
    for k, v in data.items():
        if k in mapping:
            if k in {"category", "compound"} and v is not None: 
                v = str(v).upper()
            fields.append(f'{mapping[k]} = ${len(vals)+1}')
            vals.append(v)

    if not fields: 
        raise HTTPException(400, "no updatable fields")
        
    vals.extend([current_user.id, debt_id])

    row = await conn.fetchrow(
        f"""
        UPDATE debts 
        SET {', '.join(fields)}, updated_at = now() 
        WHERE user_id = ${len(vals)-1} AND id = ${len(vals)} 
        RETURNING id, user_id, category::text AS category, 
                  loan_amount, repay_amount, interest_rate, 
                  compound::text AS compound, created_at, updated_at
        """, 
        *vals
    )
    
    res = dict(row)
    res["loan_amount"] = float(res["loan_amount"])
    res["repay_amount"] = float(res["repay_amount"])
    res["interest_rate"] = float(res["interest_rate"])
    return res

# ========= 삭제 =========
@router.delete("/{debt_id}")
async def delete_debt(
    debt_id: int, 
    current_user: CurrentUser = Depends(get_current_user), 
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    res = await conn.execute("DELETE FROM debts WHERE user_id=$1 AND id=$2", current_user.id, debt_id)
    if not res.endswith(" 1"): 
        raise HTTPException(404, "debt not found")
    return {"status": "ok", "deleted_id": debt_id}