"""نموذج الوظيفة الشاغرة (جدول jobs)."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import DEFAULT_MATCH_WEIGHTS, JOB_STATUSES
from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    """وظيفة شاغرة يمكن مطابقة المرشحين معها."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    title: Mapped[str] = mapped_column(String(150), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)

    required_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSON, default=list)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=JOB_STATUSES[1])  # "Open" افتراضياً

    match_weights: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_MATCH_WEIGHTS))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Job id={self.id} title={self.title!r} status={self.status}>"
