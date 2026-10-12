
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.enums import UserRole
from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(String(20), nullable=False, default=UserRole.RECRUITER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    allowed_pages: Mapped[list | None] = mapped_column(JSON, nullable=True)

    remember_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remember_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reset_code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reset_code_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_attempts: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"
