from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.article import Article
from app.schemas.article import ArticleCreate, ArticleOut

router = APIRouter(prefix="/articles", tags=["articles"])

@router.post("", response_model=ArticleOut, status_code=201)
def create_article(payload: ArticleCreate, db: Session = Depends(get_db)):
    obj = Article(title=payload.title, content=payload.content)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.get("", response_model=list[ArticleOut])
def list_articles(db: Session = Depends(get_db)):
    return db.query(Article).order_by(Article.id.desc()).all()

@router.get("/{article_id}", response_model=ArticleOut)
def get_article(article_id: int, db: Session = Depends(get_db)):
    obj = db.get(Article, article_id)
    if not obj:
        raise HTTPException(404, "Article not found")
    return obj

@router.delete("/{article_id}", status_code=204)
def delete_article(article_id: int, db: Session = Depends(get_db)):
    obj = db.get(Article, article_id)
    if not obj:
        raise HTTPException(404, "Article not found")
    db.delete(obj); db.commit()
