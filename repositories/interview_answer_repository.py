"""مستودع إجابات المقابلات (كل إجابة مرتبطة بمقابلة محددة، أي بمرشح محدد عبر التقديم)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.interview_answer import InterviewAnswer
from repositories.base import BaseRepository


class InterviewAnswerRepository(BaseRepository[InterviewAnswer]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, InterviewAnswer)

    def get_for_interview(self, interview_id: int) -> list[InterviewAnswer]:
        stmt = select(InterviewAnswer).where(InterviewAnswer.interview_id == interview_id)
        return list(self._session.scalars(stmt).all())

    def get_one(self, interview_id: int, question_id: int) -> InterviewAnswer | None:
        stmt = select(InterviewAnswer).where(
            InterviewAnswer.interview_id == interview_id, InterviewAnswer.question_id == question_id
        )
        return self._session.scalars(stmt).first()