import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def get_db_connection():
    return await asyncpg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        database=os.getenv("DB_NAME"),
    )
