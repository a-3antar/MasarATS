"""
إعداد الاتصال بقاعدة البيانات باستخدام SQLAlchemy.
مصمم بحيث يعمل مع SQLite الآن، وينتقل لـ PostgreSQL/SQL Server لاحقاً
بمجرد تغيير DATABASE_URL في الإعدادات دون تغيير أي كود آخر.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import get_settings
from core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """القاعدة المشتركة لكل نماذج SQLAlchemy (Models) في التطبيق."""


def _build_engine():
    settings = get_settings()
    # connect_args خاص بـ SQLite فقط للسماح باستخدامه من ثريدات متعددة (Streamlit)
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, connect_args=connect_args, echo=False)


engine = _build_engine()
# expire_on_commit=False مهم هنا: صفحات Streamlit تقرأ خصائص الكائنات (مثل candidate.full_name)
# بعد الخروج من كتلة `with get_db_session()` وإغلاق الجلسة. لو تُرك الإعداد الافتراضي (True)،
# تنتهي صلاحية كل الخصائص عند الـ commit وتحتاج جلسة حية لإعادة تحميلها، فيظهر DetachedInstanceError.
# هذا آمن هنا لأننا لا نُعدّل نفس الكائن عبر جلسة أخرى لاحقاً قبل إعادة قراءته من القاعدة.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """إنشاء كل الجداول المعرّفة إن لم تكن موجودة. تُستدعى عند بدء التطبيق."""
    # استيراد النماذج هنا (وليس أعلى الملف) لتفادي circular imports،
    # لأن كل نموذج يحتاج Base من هذا الملف.
    from models import application, candidate, job, user  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized (tables ensured).")


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager لجلسة قاعدة بيانات آمنة:
    - commit تلقائي عند النجاح
    - rollback تلقائي عند حدوث استثناء
    - إغلاق الجلسة دائماً في النهاية
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
