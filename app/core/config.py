from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DB_URL: str = "sqlite:///./dev.db"  # 나중에 Postgres로 바꾸기 쉬움
    class Config:
        env_file = ".env"

settings = Settings()