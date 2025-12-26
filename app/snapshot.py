import asyncpg
from typing import Any

async def load_user_snapshot(conn: asyncpg.Connection, user_id: int) -> dict[str, Any]:
    # 1. 저축 (Savings): category와 compound 추가
    savings = await conn.fetch("""
        SELECT 
            category::text AS category,
            amount::float AS amount, 
            interest_rate::float AS interest_rate,
            compound::text AS compound  -- ✅ 추가됨
        FROM savings
        WHERE user_id = $1
        ORDER BY created_at DESC
    """, user_id)

    # 2. 투자 (Investments): category 추가
    investments = await conn.fetch("""
        SELECT 
            category::text AS category, -- ✅ 추가됨
            amount::float AS amount, 
            roi::float AS roi,
            dividend::float AS dividend
        FROM investments
        WHERE user_id = $1
        ORDER BY created_at DESC
    """, user_id)

    # 3. 고정 자산 (Assets): category 추가
    assets = await conn.fetch("""
        SELECT
            category::text AS category,
            interest_rate::float AS interest_rate,
            roi::float           AS roi,       -- yield_rate 대신 roi 사용
            dividend::float      AS dividend,  -- 추가된 dividend 반영
            amount::float        AS amount,    -- current_amount 대신 amount 사용
            loan_amount::float   AS loan_amount,
            repay_amount::float  AS repay_amount,
            currency::text       AS currency   -- 추가된 currency 반영
        FROM assets
        WHERE user_id = $1
        ORDER BY created_at DESC
    """, user_id)
    print(assets)
    # 4. 부채 (Debts): category 추가 및 일관성 유지
    debts = await conn.fetch("""
        SELECT
            category::text AS category, -- ✅ 추가됨
            loan_amount::float   AS loan_amount,
            repay_amount::float  AS repay_amount,
            interest_rate::float AS interest_rate,
            compound::text       AS compound,
            currency::text       AS currency,
            created_at,
            updated_at
        FROM debts
        WHERE user_id = $1
        ORDER BY created_at DESC
    """, user_id)

    return {
        "savings": list(savings),
        "investments": list(investments),
        "debts": list(debts),
        "assets": list(assets)
    }

async def load_plan_snapshot(conn: asyncpg.Connection, user_id: int, plan_id: int) -> dict[str, Any]:
    # 기본 user 재정 상태 로드
    user_snapshot = await load_user_snapshot(conn, user_id)

    # 플랜 수입(revenues)
    revenues = await conn.fetch("""
        SELECT category::text AS category,
               amount::float AS amount,
               frequency::text AS frequency
        FROM revenues
        WHERE plan_id = $1
        ORDER BY created_at DESC
    """, plan_id)

    # 플랜 지출(expenses)
    expenses = await conn.fetch("""
        SELECT category::text AS category,
               amount::float AS amount,
               frequency::text AS frequency
        FROM expenses
        WHERE plan_id = $1
        ORDER BY created_at DESC
    """, plan_id)

    return {
        **user_snapshot,
        "revenues": list(revenues),
        "expenses": list(expenses),
    }