from fastapi import APIRouter, Depends, HTTPException
import asyncpg
from app.db import get_db_connection
from app.schemas.schemas import AssetCreate, AssetUpdate, AssetOut
from app.auth import get_current_user, CurrentUser

router = APIRouter(prefix="/assets", tags=["assets"])

# ✅ 조회 함수: 리턴 시 float 변환 직접 수행
async def get_assets_data(user_id: int, conn: asyncpg.Connection):
    return await conn.fetch(
        """
        SELECT
            id, user_id,
            category::text AS category,
            interest_rate, roi, dividend,
            amount,
            loan_amount, repay_amount,
            created_at, updated_at
        FROM assets
        WHERE user_id = $1
        ORDER BY created_at DESC NULLS LAST, id DESC
        """,
        user_id,
    )

# ========= 목록 조회 =========
@router.get("/", response_model=list[AssetOut])
async def list_assets(
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    rows = await get_assets_data(current_user.id, conn)

    return [
        {
            **dict(r),
            "interest_rate": float(r["interest_rate"]) if r["interest_rate"] is not None else None,
            "roi": float(r["roi"]) if r["roi"] is not None else None,
            "dividend": float(r["dividend"]) if r["dividend"] is not None else None,
            "amount": float(r["amount"]) if r["amount"] is not None else 0.0,
            "loan_amount": float(r["loan_amount"]) if r["loan_amount"] is not None else 0.0,
            "repay_amount": float(r["repay_amount"]) if r["repay_amount"] is not None else 0.0,
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

    # 상환액 검증 로직 (f 함수 제거)
    loan_val = payload.loan_amount or 0
    if loan_val > 0:
        rate_val = payload.interest_rate or 0
        repay_val = payload.repay_amount or 0
        monthly_interest = (loan_val * (rate_val / 100)) / 12
        if repay_val < monthly_interest:
            raise HTTPException(
                status_code=400, 
                detail=f"상환액(₩{repay_val:,.0f})이 월 이자(₩{monthly_interest:,.0f})보다 적어 부채가 무한히 증식합니다."
            )
    
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO assets
                (user_id, category, interest_rate, roi, dividend,
                 amount, loan_amount, repay_amount)
            VALUES
                ($1, $2, $3, $4, $5,
                 $6, $7, $8)
            RETURNING
                id, user_id, category::text AS category,
                interest_rate, roi, dividend,
                amount,
                loan_amount, repay_amount,
                created_at, updated_at
            """,
            current_user.id,
            payload.category.upper(),
            payload.interest_rate,
            payload.roi,
            payload.dividend,
            payload.amount,
            payload.loan_amount,
            payload.repay_amount,
        )

    return {
        **dict(row),
        "interest_rate": float(row["interest_rate"]) if row["interest_rate"] is not None else None,
        "roi": float(row["roi"]) if row["roi"] is not None else None,
        "dividend": float(row["dividend"]) if row["dividend"] is not None else None,
        "amount": float(row["amount"]),
        "loan_amount": float(row["loan_amount"]),
        "repay_amount": float(row["repay_amount"]),
    }

# ========= 부분 수정 =========
@router.patch("/{asset_id}", response_model=AssetOut)
async def update_asset(
    asset_id: int,
    payload: AssetUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    existing = await conn.fetchrow(
        "SELECT loan_amount, interest_rate, repay_amount FROM assets WHERE id = $1 AND user_id = $2",
        asset_id, current_user.id
    )
    if not existing:
        raise HTTPException(404, "asset not found")

    data = payload.model_dump(exclude_unset=True)
    
    # 검증용 값 계산 (f 함수 없이 직접 처리)
    new_loan = data.get("loan_amount", existing["loan_amount"]) or 0
    new_rate = data.get("interest_rate", existing["interest_rate"]) or 0
    new_repay = data.get("repay_amount", existing["repay_amount"]) or 0

    if float(new_loan) > 0:
        monthly_interest = (float(new_loan) * (float(new_rate) / 100)) / 12
        if float(new_repay) < monthly_interest:
            raise HTTPException(
                status_code=400, 
                detail=f"수정 후 상환액(₩{float(new_repay):,.0f})이 월 이자(₩{monthly_interest:,.0f})보다 적습니다."
            )

    mapping = {
        "category": "category",
        "interest_rate": "interest_rate",
        "roi": "roi",
        "dividend": "dividend",
        "amount": "amount",
        "loan_amount": "loan_amount",
        "repay_amount": "repay_amount",
    }

    fields, vals = [], []
    for k, v in data.items():
        if k in mapping:
            if k == "category" and v is not None:
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
            amount,
            loan_amount, repay_amount,
            created_at, updated_at
    """

    row = await conn.fetchrow(q, *vals)
    if not row:
        raise HTTPException(404, "asset not found")

    return {
        **dict(row),
        "interest_rate": float(row["interest_rate"]) if row["interest_rate"] is not None else None,
        "roi": float(row["roi"]) if row["roi"] is not None else None,
        "dividend": float(row["dividend"]) if row["dividend"] is not None else None,
        "amount": float(row["amount"]),
        "loan_amount": float(row["loan_amount"]),
        "repay_amount": float(row["repay_amount"]),
    }


# ========= 삭제 (기존 동일) =========
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