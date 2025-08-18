# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Money Back API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Item(BaseModel):
    name: str
    price: float

@app.get("/items")
def get_items():
    return [
        {"name": "Apple", "price": 1.2},
        {"name": "Banana", "price": 0.8},
    ]

@app.post("/items")
def create_item(item: Item):
    return {"message": "Item created", "item": item}
