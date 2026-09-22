"""
إعداد الاتصال بقاعدة البيانات باستخدام SQLAlchemy.
مصمم بحيث يعمل مع SQLite الآن، وينتقل لـ PostgreSQL/SQL Server لاحقاً
بمجرد تغيير DATABASE_URL في الإعدادات دون تغيير أي كود آخر.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import get_settings
from core.logging import get_logger



logger = get_logger(__name__)


class Base(DeclarativeBase):
    """القاعدة المشتركة لكل نماذج SQLAlchemy (Models) في التطبيق."""

def _build_engine():
    settings = get_settings()
    # connect_args خاص بـ SQLite: السماح بالوصول من عدة ثريدات + مهلة انتظار عند القفل
    # بدل الفشل الفوري (ضروري الآن لأن رفع عدة سير ذاتية يُعالَج بالتوازي في عدة Threads).
    connect_args = (
        {"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {}
    )
    engine = create_engine(settings.database_url, connect_args=connect_args, echo=False)

    if settings.database_url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _):
            # WAL يسمح بقراءة/كتابة متزامنة أفضل من وضع SQLite الافتراضي (DELETE journal mode)
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return engine

engine = _build_engine()
# expire_on_commit=False مهم هنا: صفحات Streamlit تقرأ خصائص الكائنات (مثل candidate.full_name)
# بعد الخروج من كتلة `with get_db_session()` وإغلاق الجلسة. لو تُرك الإعداد الافتراضي (True)،
# تنتهي صلاحية كل الخصائص عند الـ commit وتحتاج جلسة حية لإعادة تحميلها، فيظهر DetachedInstanceError.
# هذا آمن هنا لأننا لا نُعدّل نفس الكائن عبر جلسة أخرى لاحقاً قبل إعادة قراءته من القاعدة.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _add_missing_columns() -> None:
    """
    يضيف أي أعمدة جديدة في النماذج لجداول موجودة مسبقاً في القاعدة.
    ضروري لأن create_all() ينشئ الجداول الناقصة فقط ولا يعدّل الجداول القائمة.
    """
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                column_type = column.type.compile(dialect=engine.dialect)
                connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type}"))
                logger.info("Added missing column %s.%s", table.name, column.name)


def init_db() -> None:
    """إنشاء كل الجداول المعرّفة إن لم تكن موجودة + إضافة الأعمدة الناقصة. تُستدعى عند بدء التطبيق."""
    # استيراد النماذج هنا (وليس أعلى الملف) لتفادي circular imports،
    # لأن كل نموذج يحتاج Base من هذا الملف.
    from models import application, candidate, interview, job, user  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
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
