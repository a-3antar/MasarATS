"""نموذج سؤال مقابلة مرتبط بوظيفة - بنك أسئلة قابل لإعادة الاستخدام مع أي مرشح متقدم لنفس الوظيفة."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobQuestion(Base):
    """سؤال ضمن بنك أسئلة وظيفة معينة."""

    __tablename__ = "job_questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)

    question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)  # cv_specific/technical/behavioral/leadership أو null (يدوي)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="manual", nullable=False)  # "ai" أو "manual"

    # نوع السؤال: text / choice / rating (NULL في السجلات القديمة = text)
    question_type: Mapped[str | None] = mapped_column(String(10), default="text", nullable=True)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)  # خيارات سؤال الاختيار من متعدد
    competency: Mapped[str | None] = mapped_column(String(100), nullable=True)  # الكفاءة التي يقيسها السؤال
    difficulty: Mapped[str | None] = mapped_column(String(10), nullable=True)  # Low / Medium / High

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<JobQuestion id={self.id} job_id={self.job_id}>"