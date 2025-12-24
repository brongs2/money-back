import asyncpg
from typing import Any

async def load_user_snapshot(conn: asyncpg.Connection, user_id: int) -> dict[str, Any]:
    savings = await conn.fetch("""
        SELECT amount::float AS amount, interest_rate::float AS interest_rate
        FROM savings
        WHERE user_id = $1
    """, user_id)

    investments = await conn.fetch("""
        SELECT amount::float AS amount, yield_rate::float AS yield_rate
        FROM investments
        WHERE user_id = $1
    """, user_id)


    assets = await conn.fetch(
        """
        SELECT
            has_loan,
            interest_rate::float AS interest_rate,
            yield_rate::float    AS yield_rate,
            purchase_amount::float AS purchase_amount,
            current_amount::float  AS current_amount,
            loan_amount::float     AS loan_amount,
            repay_amount::float    AS repay_amount
        FROM assets
        WHERE user_id = $1
        """,
        user_id,
    )

    # 부채
    debts = await conn.fetch(
        """
        SELECT
            loan_amount::float   AS loan_amount,
            repay_amount::float  AS repay_amount,
            interest_rate::float AS interest_rate,
            compound::text       AS compound,
            currency::text       AS currency,
            created_at,
            updated_at
        FROM debts
        WHERE user_id = $1
        """,
        user_id,
    )


    return {
        "savings": savings,
        "investments": investments,
        "debts": debts,
        "assets" : assets


    }
async def load_plan_snapshot(conn, user_id: int, plan_id: int):
    # 기본 user 재정 상태
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
