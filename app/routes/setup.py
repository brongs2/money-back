# app/routes/setup.py
from fastapi import APIRouter, HTTPException, Request, Body
from app.db import get_db_connection

router = APIRouter(prefix="/setup", tags=["setup"])

# 허용 ENUM(검증 최소한)
GENDER = {"MALE", "FEMALE", "OTHER"}
CURRENCY = {"KRW", "USD", "JPY", "EUR"}
SAVING_TYPE = {"DEPOSIT", "INSTALLMENT", "CASH", "SUBSCRIPTION"}
INVEST_TYPE = {"STOCK", "BOND", "ETF", "FUND", "CRYPTO"}
ASSET_TYPE = {"HOUSE", "JEWELRY", "REAL_ESTATE"}
DEBT_TYPE = {"STUDENT_LOAN", "CREDIT_LOAN", "LIVING_EXPENSE_LOAN", "MORTGAGE"}
COMPOUND = {"SIMPLE", "COMPOUND"}

@router.post("")
async def setup(payload: dict = Body(...)):
    user = (payload.get("user") or {})
    savings = payload.get("savings") or []
    investments = payload.get("investments") or []
    assets = payload.get("assets") or []
    debts = payload.get("debts") or []
    upsert = bool(payload.get("upsert", False))

    username = user.get("username")
    if not username:
        raise HTTPException(400, "user.username is required")

    # 간단 검증(ENUM 대문자)
    if user.get("gender"):
        g = str(user["gender"]).upper()
        if g not in GENDER:
            raise HTTPException(400, f"invalid gender: {g}")
        user["gender"] = g

    # 각 배열 ENUM 대문자 보정
    def upper_enum(item, key, allowed):
        if item.get(key) is not None:
            v = str(item[key]).upper()
            if v not in allowed:
                raise HTTPException(400, f"invalid {key}: {v}")
            item[key] = v

    for s in savings:
        upper_enum(s, "category", SAVING_TYPE)
        upper_enum(s, "currency", CURRENCY)

    for inv in investments:
        upper_enum(inv, "category", INVEST_TYPE)
        upper_enum(inv, "currency", CURRENCY)

    for a in assets:
        upper_enum(a, "category", ASSET_TYPE)
        upper_enum(a, "purchase_ccy", CURRENCY)
        upper_enum(a, "current_ccy", CURRENCY)
        upper_enum(a, "loan_ccy", CURRENCY)
        upper_enum(a, "repay_ccy", CURRENCY)

    for d in debts:
        upper_enum(d, "category", DEBT_TYPE)
        upper_enum(d, "loan_ccy", CURRENCY)
        upper_enum(d, "repay_ccy", CURRENCY)
        upper_enum(d, "currency", CURRENCY)
        upper_enum(d, "compound", COMPOUND)

    conn = await get_db_connection()
    try:
        async with conn.transaction():
            # upsert: username 기준으로 기존 행/관련 데이터 정리
            existing = await conn.fetchrow("SELECT id FROM users WHERE username=$1", username)
            if existing:
                if not upsert:
                    raise HTTPException(409, "username already exists (set upsert=true to overwrite)")
                user_id = existing["id"]
                # 자식들 삭제 후 다시 입력 (ON DELETE CASCADE가 없으므로 직접 삭제)
                await conn.execute("DELETE FROM savings WHERE user_id=$1", user_id)
                await conn.execute("DELETE FROM investments WHERE user_id=$1", user_id)
                await conn.execute("DELETE FROM assets WHERE user_id=$1", user_id)
                await conn.execute("DELETE FROM debts WHERE user_id=$1", user_id)

                # 유저 기본정보 업데이트
                await conn.execute(
                    """
                    UPDATE users
                       SET birth = $2,
                           gender = $3,
                           updated_at = now()
                     WHERE id = $1
                    """,
                    user_id, user.get("birth"), user.get("gender")
                )
            else:
                # 사용자 신규 생성
                row = await conn.fetchrow(
                    """
                    INSERT INTO users (username, birth, gender)
                    VALUES ($1, $2, $3)
                    RETURNING id
                    """,
                    username, user.get("birth"), user.get("gender")
                )
                user_id = row["id"]

            # savings
            for s in savings:
                await conn.execute(
                    """
                    INSERT INTO savings
                        (user_id, category, name, amount, interest_rate, currency)
                    VALUES ($1, $2, $3, $4, $5, COALESCE($6, 'KRW'::currency))
                    """,
                    user_id, s.get("category"), s.get("name"),
                    s.get("amount", 0), s.get("interest_rate"), s.get("currency")
                )

            # investments
            for inv in investments:
                await conn.execute(
                    """
                    INSERT INTO investments
                        (user_id, category, symbol, name, amount, yield_rate, currency)
                    VALUES ($1, $2, $3, $4, $5, $6, COALESCE($7, 'KRW'::currency))
                    """,
                    user_id, inv.get("category"), inv.get("symbol"), inv.get("name"),
                    inv.get("amount", 0), inv.get("yield_rate"), inv.get("currency")
                )

            # assets
            for a in assets:
                await conn.execute(
                    """
                    INSERT INTO assets
                        (user_id, category, has_loan, interest_rate, yield_rate,
                         purchase_amount, purchase_ccy, current_amount, current_ccy,
                         loan_amount, loan_ccy, repay_amount, repay_ccy)
                    VALUES ($1, $2, COALESCE($3,false), $4, $5,
                            $6, $7, $8, $9, $10, $11, $12, $13)
                    """,
                    user_id, a.get("category"), a.get("has_loan"),
                    a.get("interest_rate"), a.get("yield_rate"),
                    a.get("purchase_amount"), a.get("purchase_ccy"),
                    a.get("current_amount"), a.get("current_ccy"),
                    a.get("loan_amount"), a.get("loan_ccy"),
                    a.get("repay_amount"), a.get("repay_ccy")
                )

            # debts
            for d in debts:
                await conn.execute(
                    """
                    INSERT INTO debts
                        (user_id, category, loan_amount, loan_ccy,
                         repay_amount, repay_ccy, interest_rate, compound, currency)
                    VALUES ($1, $2, $3, $4, $5, $6, $7,
                            COALESCE($8, 'COMPOUND'::compound),
                            COALESCE($9, 'KRW'::currency))
                    """,
                    user_id, d.get("category"),
                    d.get("loan_amount"), d.get("loan_ccy"),
                    d.get("repay_amount"), d.get("repay_ccy"),
                    d.get("interest_rate"), d.get("compound"), d.get("currency")
                )

        return {"status": "ok", "user_id": user_id,
                "counts": {"savings": len(savings), "investments": len(investments),
                           "assets": len(assets), "debts": len(debts)}}

    except HTTPException:
        raise
    except Exception as e:
        # 에러 메시지 그대로 노출이 싫으면 메시지 가공
        raise HTTPException(400, f"setup failed: {e}")
    finally:
        await conn.close()
