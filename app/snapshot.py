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

    debts = await conn.fetch("""
        SELECT loan_amount::float AS loan_amount,
               repay_amount::float AS repay_amount,
               interest_rate::float AS interest_rate
        FROM debts
        WHERE user_id = $1
    """, user_id)

    # (선택) plan 기반 월 소득 / 세금
    # 여기서는 아주 단순히 revenue의 합만 가져온다고 가정
    revenues = await conn.fetch("""
        SELECT amount::float AS amount
        FROM revenues r
        JOIN plans p ON p.id = r.plan_id
        WHERE p.user_id = $1
    """, user_id)

    taxes = await conn.fetch("""
        SELECT 0.0::float AS amount
        WHERE FALSE
    """)  # 아직 없으면 일단 0 처리 or TODO

    return {
        "savings": savings,
        "investments": investments,
        "debts": debts,
        "revenues": revenues,
        "taxes": taxes,
    }
