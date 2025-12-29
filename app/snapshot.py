import asyncpg
from typing import Any

async def load_user_snapshot(conn: asyncpg.Connection, user_id: int) -> dict[str, Any]:
    # 1. 저축 (Savings): deposit, frequency, maturity_date 추가 / currency 제거
    savings = await conn.fetch("""
        SELECT 
            category::text AS category,
            amount::float AS amount, 
            interest_rate::float AS interest_rate,
            compound::text AS compound,
            deposit::float AS deposit,                         -- ✅ 추가
            deposit_frequency::text AS deposit_frequency,       -- ✅ 추가
            maturity_date                                       -- ✅ 추가
        FROM savings
        WHERE user_id = $1
        ORDER BY created_at DESC
    """, user_id)

    # 2. 투자 (Investments): deposit, frequency, maturity_date 추가 / currency 제거
    investments = await conn.fetch("""
        SELECT 
            category::text AS category,
            amount::float AS amount, 
            roi::float AS roi,
            dividend::float AS dividend,
            deposit::float AS deposit,                         -- ✅ 추가
            deposit_frequency::text AS deposit_frequency,       -- ✅ 추가
            maturity_date                                       -- ✅ 추가
        FROM investments
        WHERE user_id = $1
        ORDER BY created_at DESC
    """, user_id)

    # 3. 고정 자산 (Assets): currency 제거
    assets = await conn.fetch("""
        SELECT
            category::text AS category,
            interest_rate::float AS interest_rate,
            roi::float           AS roi,
            dividend::float      AS dividend,
            amount::float        AS amount,
            loan_amount::float   AS loan_amount,
            repay_amount::float  AS repay_amount
            -- currency 제거됨
        FROM assets
        WHERE user_id = $1
        ORDER BY created_at DESC
    """, user_id)

    # 4. 부채 (Debts): currency 제거
    debts = await conn.fetch("""
        SELECT
            category::text AS category,
            loan_amount::float   AS loan_amount,
            repay_amount::float  AS repay_amount,
            interest_rate::float AS interest_rate,
            compound::text       AS compound
            -- currency 제거됨
        FROM debts
        WHERE user_id = $1
        ORDER BY created_at DESC
    """, user_id)

    return {
        "savings": [dict(r) for r in savings],
        "investments": [dict(r) for r in investments],
        "debts": [dict(r) for r in debts],
        "assets": [dict(r) for r in assets]
    }

async def load_plan_snapshot(conn: asyncpg.Connection, user_id: int, plan_id: int) -> dict[str, Any]:
    # 기본 user 재정 상태 로드 (Savings, Investments, Assets, Debts 등)
    user_snapshot = await load_user_snapshot(conn, user_id)

    # 플랜 수입(revenues) 로드: start_date, end_date 추가
    revenues = await conn.fetch("""
        SELECT category::text AS category,
               amount::float AS amount,
               frequency::text AS frequency,
               start_date,
               end_date
        FROM revenues
        WHERE plan_id = $1
        ORDER BY created_at DESC
    """, plan_id)

    # 플랜 지출(expenses) 로드: start_date, end_date 추가
    expenses = await conn.fetch("""
        SELECT category::text AS category,
               amount::float AS amount,
               frequency::text AS frequency,
               start_date,
               end_date
        FROM expenses
        WHERE plan_id = $1
        ORDER BY created_at DESC
    """, plan_id)
    return {
        **user_snapshot,
        "revenues": [dict(r) for r in revenues],
        "expenses": [dict(r) for r in expenses],
    }