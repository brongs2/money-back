from pydantic import BaseModel

class ArticleBase(BaseModel):
    title: str
    content: str

class ArticleCreate(ArticleBase):
    pass

class ArticleOut(ArticleBase):
    id: int
