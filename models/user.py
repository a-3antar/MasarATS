"""نموذج المستخدم (جدول users) — يمثل حسابات الدخول إلى النظام."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from core.enums import UserRole
from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """مستخدم مسجّل في نظام SmartATS AI."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(String(20), nullable=False, default=UserRole.RECRUITER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # دعم خاصية "تذكرني": توكن عشوائي مشفّر بنفس آلية كلمة المرور (bcrypt) - وليس كلمة
    # المرور نفسها أبداً. يُخزَّن في كوكيز المتصفح فقط uid + التوكن الخام، وهذا العمود
    # يحمل الـ hash فقط، تماماً كما يُخزَّن password_hash. تغيير كلمة المرور لا يمسحه
    # تلقائياً في هذه المرحلة - يمكن إبطاله يدوياً من الإعدادات لاحقاً إن لزم.
    remember_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remember_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"
