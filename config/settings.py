"""
إعدادات التطبيق المركزية.
تُقرأ من متغيرات البيئة (.env) بحيث لا تُكتب أي قيم حساسة داخل الكود مباشرة.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """إعدادات التطبيق. تُملأ تلقائياً من ملف .env أو متغيرات البيئة."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # عام
    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "dev-secret-change-me"

    # قاعدة البيانات
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'smartats.db'}"

    # الذكاء الاصطناعي (سيُستخدم في مرحلة لاحقة)
    gemini_api_key: str = ""
    ai_model: str = "gemini-flash-lite-latest"
    ai_temperature: float = 0.2

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    """إرجاع نسخة واحدة مخزّنة (cached) من الإعدادات لتفادي إعادة القراءة من الملف في كل استدعاء."""
    return Settings()
