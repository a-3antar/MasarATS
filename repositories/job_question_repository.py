"""مستودع أسئلة الوظيفة (بنك أسئلة مشترك بين كل المرشحين المتقدمين لنفس الوظيفة)."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models.job_question import JobQuestion
from repositories.base import BaseRepository


class JobQuestionRepository(BaseRepository[JobQuestion]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, JobQuestion)

    def get_for_job(self, job_id: int) -> list[JobQuestion]:
        stmt = select(JobQuestion).where(JobQuestion.job_id == job_id).order_by(JobQuestion.id)
        return list(self._session.scalars(stmt).all())

    def delete_for_job(self, job_id: int) -> None:
        self._session.execute(delete(JobQuestion).where(JobQuestion.job_id == job_id))