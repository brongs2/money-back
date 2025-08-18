from fastapi import FastAPI
from ..db.session import get_db
from ..models.article import Article
from ..schemas.article import ArticleCreate, ArticleOut

app = FastAPI(title="News API")

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)  # 초기 테이블 생성

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(articles_router)
