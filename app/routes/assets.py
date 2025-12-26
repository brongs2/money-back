from fastapi import APIRouter, Depends, HTTPException
import asyncpg
import json

from app.db import get_db_connection
from app.schemas.schemas import AssetCreate, AssetUpdate, AssetOut
from app.auth import get_current_user, CurrentUser

router = APIRouter(prefix="/assets", tags=["assets"])

# 공통 데이터 변환 함수
def f(v): return float(v) if v is not None else None

# ✅ 대시보드 및 타 서비스에서 재사용할 공통 조회 함수
async def get_assets_data(user_id: int, conn: asyncpg.Connection):
    return await conn.fetch(
        """
        SELECT
            id, user_id,
            category::text AS category,
            interest_rate, roi, dividend,
            amount, currency::text AS currency,
            loan_amount, repay_amount,
            created_at, updated_at
        FROM assets
        WHERE user_id = $1
        ORDER BY created_at DESC NULLS LAST, id DESC
        """,
        user_id,
    )

# ========= 목록 조회 (내 assets만) =========
@router.get("/", response_model=list[AssetOut])
async def list_assets(
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    rows = await get_assets_data(current_user.id, conn)

    return [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "category": r["category"],
            "interest_rate": f(r["interest_rate"]),
            "roi": f(r["roi"]),
            "dividend": f(r["dividend"]),
            "amount": f(r["amount"]),
            "currency": r["currency"],
            "loan_amount": f(r["loan_amount"]),
            "repay_amount": f(r["repay_amount"]),
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


    loan_amount = f(payload.loan_amount) or 0
    if loan_amount > 0:
        monthly_interest = (loan_amount * (f(payload.interest_rate) / 100)) / 12
        if f(payload.repay_amount) < monthly_interest:
            raise HTTPException(
                status_code=400, 
                detail=f"상환액(₩{payload.repay_amount:,.0f})이 월 이자(₩{monthly_interest:,.0f})보다 적어 부채가 무한히 증식합니다."
            )
    def up(v): return v.upper() if isinstance(v, str) else v
    # 상환액이 금리보다 높아야함
    
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO assets
                (user_id, category, interest_rate, roi, dividend,
                 amount, currency, loan_amount, repay_amount)
            VALUES
                ($1, $2, $3, $4, $5,
                 $6, $7, $8, $9)
            RETURNING
                id, user_id, category::text AS category,
                interest_rate, roi, dividend,
                amount, currency::text AS currency,
                loan_amount, repay_amount,
                created_at, updated_at
            """,
            current_user.id,
            up(payload.category),
            payload.interest_rate,
            payload.roi,
            payload.dividend,
            payload.amount,
            up(payload.currency),
            payload.loan_amount,
            payload.repay_amount,
        )

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "category": row["category"],
        "interest_rate": f(row["interest_rate"]),
        "roi": f(row["roi"]),
        "dividend": f(row["dividend"]),
        "amount": f(row["amount"]),
        "currency": row["currency"],
        "loan_amount": f(row["loan_amount"]),
        "repay_amount": f(row["repay_amount"]),
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
    
    # 1. 기존 데이터 조회 (검증을 위해 필요)
    existing = await conn.fetchrow(
        "SELECT loan_amount, interest_rate, repay_amount FROM assets WHERE id = $1 AND user_id = $2",
        asset_id, current_user.id
    )
    if not existing:
        raise HTTPException(404, "asset not found")

    # 2. 업데이트할 데이터와 기존 데이터를 합쳐서 검증용 값 생성
    data = payload.model_dump(exclude_unset=True)
    
    new_loan = data.get("loan_amount", existing["loan_amount"])
    new_rate = data.get("interest_rate", existing["interest_rate"])
    new_repay = data.get("repay_amount", existing["repay_amount"])

    # 3. 상환액 검증 (수정 후의 상태 기준)
    loan_val = f(new_loan) or 0
    if loan_val > 0:
        monthly_interest = (loan_val * (f(new_rate) / 100)) / 12
        if f(new_repay) < monthly_interest:
            raise HTTPException(
                status_code=400, 
                detail=f"수정 후 상환액(₩{new_repay:,.0f})이 월 이자(₩{monthly_interest:,.0f})보다 적습니다."
            )
    # 변경된 컬럼명 매핑
    mapping = {
        "category": "category",
        "interest_rate": "interest_rate",
        "roi": "roi",
        "dividend": "dividend",
        "amount": "amount",
        "currency": "currency",
        "loan_amount": "loan_amount",
        "repay_amount": "repay_amount",
    }

    data = payload.model_dump(exclude_unset=True)
    fields, vals = [], []
    
    for k, v in data.items():
        if k in mapping:
            if k in {"category", "currency"} and v is not None:
                v = str(v).upper()
            fields.append(f'{mapping[k]} = ${len(vals)+1}')
            vals.append(v)


    if not fields:
        raise HTTPException(400, "no updatable fields")

    vals.extend([current_user.id, asset_id])

    q = f"""
        UPDATE assets
           SET {', '.join(fields)}, updated_at = now()
         WHERE user_id = ${len(vals)-1} AND id = ${len(vals)}
        RETURNING
            id, user_id, category::text AS category,
            interest_rate, roi, dividend,
            amount, currency::text AS currency,
            loan_amount, repay_amount,
            created_at, updated_at
    """

    row = await conn.fetchrow(q, *vals)
    if not row:
        raise HTTPException(404, "asset not found")

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "category": row["category"],
        "interest_rate": f(row["interest_rate"]),
        "roi": f(row["roi"]),
        "dividend": f(row["dividend"]),
        "amount": f(row["amount"]),
        "currency": row["currency"],
        "loan_amount": f(row["loan_amount"]),
        "repay_amount": f(row["repay_amount"]),
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