from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    groq_api_key: str
    gemini_api_key: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    user_password: str
    access_token_expire_hours: int = 8760  # 1 year

    # All paths — Windows
    base_dir: str = r"C:\KING"

    @property
    def db_path(self) -> str:
        return os.path.join(self.base_dir, "data", "king.db")

    @property
    def chronicle_db_path(self) -> str:
        return os.path.join(self.base_dir, "data", "chronicle.db")

    @property
    def instinct_db_path(self) -> str:
        return os.path.join(self.base_dir, "data", "instinct.db")

    @property
    def log_path(self) -> str:
        return os.path.join(self.base_dir, "logs", "king.log")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
