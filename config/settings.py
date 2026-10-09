"""
إعدادات التطبيق المركزية.
تُقرأ من متغيرات البيئة (.env) بحيث لا تُكتب أي قيم حساسة داخل الكود مباشرة.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
    log_level: str = "DEBUG"
    secret_key: str = "dev-secret-change-me"

    # قاعدة البيانات
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'smartats.db'}"

    # الذكاء الاصطناعي
    gemini_api_key: str = ""
    alt_gemini_api_key: str = Field(default="", validation_alias="ALT_GEMINI_KEY")
    ai_model: str = "gemini-flash-lite-latest"
    ai_temperature: float = 0.2

    # البريد (SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = "learningosra@gmail.com"
    smtp_password: str = "ljxt exee hqan aykq"
    smtp_from: str = "learningosra@gmail.com"
    smtp_use_tls: bool = True

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def ai_enabled(self) -> bool:
        """هل يوجد أي مفتاح Gemini مضبوط (الرئيسي أو الاحتياطي)؟"""
        return bool(self.gemini_api_key or self.alt_gemini_api_key)

    @property
    def email_enabled(self) -> bool:
        """هل إعدادات SMTP كافية لإرسال البريد؟"""
        return bool(self.smtp_host and (self.smtp_from or self.smtp_user))


@lru_cache
def get_settings() -> Settings:
    """إرجاع نسخة واحدة مخزّنة (cached) من الإعدادات لتفادي إعادة القراءة من الملف في كل استدعاء."""
    return Settings()