from fastapi import FastAPI, Depends, Request
from app.routes import setup, users, savings, investments, assets, debts, plans
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.db import get_db_connection
from app.auth import get_current_user, CurrentUser  # 너가 정의한 거 기준
import asyncpg

app = FastAPI()
# 정적 파일 (css, js)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 템플릿 폴더
templates = Jinja2Templates(directory="app/templates")
app.include_router(setup.router)
# app.include_router(users.router)
app.include_router(savings.router)
app.include_router(investments.router)
app.include_router(assets.router)
app.include_router(debts.router)
app.include_router(plans.router)

@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    # 예: 현재 유저의 savings / investments / debts 간단 조회
    savings = await conn.fetch(
        """
        SELECT category::text AS category, name, amount::float AS amount
        FROM savings
        WHERE user_id = $1
        ORDER BY created_at DESC
        """,
        current_user.id,
    )

    investments = await conn.fetch(
        """
        SELECT category::text AS category, name, amount::float AS amount
        FROM investments
        WHERE user_id = $1
        ORDER BY created_at DESC
        """,
        current_user.id,
    )

    debts = await conn.fetch(
        """
        SELECT category::text AS category, loan_amount::float AS loan_amount
        FROM debts
        WHERE user_id = $1
        ORDER BY created_at DESC
        """,
        current_user.id,
    )

    # 템플릿 렌더링
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "savings": list(savings),
            "investments": list(investments),
            "debts": list(debts),
        },
    )