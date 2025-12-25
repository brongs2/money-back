from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncpg
from datetime import date

# 우리가 만든 모듈들 임포트
from app.db import get_db_connection
from app.auth import get_current_user, CurrentUser
from app.snapshot import load_user_snapshot  # 💡 스냅샷 함수 활용
from app.routes import savings, investments, assets, debts, plans

# ✅ 1. 'app' 인스턴스를 가장 먼저 생성해야 합니다!
app = FastAPI()

# ✅ 2. 설정 (Static, Templates)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ✅ 3. 라우터 등록
app.include_router(savings.router)
app.include_router(investments.router)
app.include_router(assets.router)
app.include_router(debts.router)
app.include_router(plans.router)

# ✅ 4. 대시보드 (이제 'app'이 정의되었으므로 에러가 나지 않습니다)
@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    # 테스트용이므로 이미 있는 load_user_snapshot을 재활용하는 것이 가장 빠릅니다.
    snapshot = await load_user_snapshot(conn, current_user.id)
    
    # 플랜 목록만 따로 조회
    plans_data = await conn.fetch(
        "SELECT id, title, description FROM plans WHERE user_id = $1 ORDER BY created_at DESC",
        current_user.id
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "savings": snapshot.get("savings", []),
            "investments": snapshot.get("investments", []),
            "assets": snapshot.get("assets", []),
            "debts": snapshot.get("debts", []),
            "plans": plans_data,
        },
    )