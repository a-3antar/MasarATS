
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import INTERVIEW_STATUSES, INTERVIEW_TYPES
from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Interview(Base):

    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)

    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)

    interview_type: Mapped[str] = mapped_column(String(20), default=INTERVIEW_TYPES[0], nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=INTERVIEW_STATUSES[0], nullable=False)

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interviewer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    questions: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(255), nullable=True)

    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    overall_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Interview id={self.id} application_id={self.application_id} type={self.interview_type}>"
