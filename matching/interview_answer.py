"""نموذج إجابة مرشح على سؤال من بنك أسئلة الوظيفة، ضمن مقابلة محددة (= مرتبطة بمرشح عبر التقديم)."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewAnswer(Base):
    """إجابة واحدة على سؤال واحد ضمن مقابلة واحدة، مع تقييمها."""

    __tablename__ = "interview_answers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), nullable=False, index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("job_questions.id"), nullable=False, index=True)

    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    eval_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 إلى 5
    eval_method: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "ai" أو "manual"
    eval_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    eval_strengths: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    eval_concerns: Mapped[list] = mapped_column(JSON, default=list, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<InterviewAnswer interview_id={self.interview_id} question_id={self.question_id}>"
    