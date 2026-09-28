"""إجابة مرشح على سؤال من بنك أسئلة الوظيفة ضمن مقابلة محددة.
تقييم الذكاء الاصطناعي وتقييم المُقابِل مخزَّنان منفصلين؛ eval_score هي الدرجة الفعلية
(درجة المُقابِل إن وُجدت وإلا درجة الذكاء الاصطناعي)."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewAnswer(Base):
    __tablename__ = "interview_answers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), nullable=False, index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("job_questions.id"), nullable=False, index=True)

    answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    # تحليل الذكاء الاصطناعي (1 إلى 5 + أبعاد من 100 + سؤال متابعة مقترح)
    ai_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_dimensions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_followup: Mapped[str | None] = mapped_column(Text, nullable=True)
    eval_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    eval_strengths: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    eval_concerns: Mapped[list] = mapped_column(JSON, default=list, nullable=True)

    # تقييم المُقابِل (1 إلى 5) وملاحظاته
    manual_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # الدرجة الفعلية (1 إلى 5) ومصدرها "ai" أو "manual"
    eval_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eval_method: Mapped[str | None] = mapped_column(String(10), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<InterviewAnswer interview_id={self.interview_id} question_id={self.question_id}>"