"""مستودع المقابلات: استعلامات خاصة بجدول interviews."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.application import Application
from models.candidate import Candidate
from models.interview import Interview
from models.job import Job
from repositories.base import BaseRepository


class InterviewRepository(BaseRepository[Interview]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Interview)

    def get_for_application(self, application_id: int) -> list[Interview]:
        stmt = (
            select(Interview)
            .where(Interview.application_id == application_id)
            .order_by(Interview.scheduled_at.desc())
        )
        return list(self._session.scalars(stmt).all())

    def list_for_candidate(self, candidate_id: int) -> list[tuple[Interview, Job]]:
        """كل مقابلات مرشح (عبر كل وظائفه) مع الوظيفة، الأحدث أولاً - لعرض سجل المقابلات السابقة."""
        stmt = (
            select(Interview, Job)
            .join(Application, Application.id == Interview.application_id)
            .join(Job, Job.id == Application.job_id)
            .where(Application.candidate_id == candidate_id)
            .order_by(Interview.scheduled_at.desc())
        )
        return [(row[0], row[1]) for row in self._session.execute(stmt).all()]

    def list_all_with_context(self) -> list[tuple[Interview, Candidate, Job]]:
        """كل المقابلات مع المرشح والوظيفة المرتبطين بها (لعرض التقويم الموحّد)."""
        stmt = (
            select(Interview, Candidate, Job)
            .join(Application, Application.id == Interview.application_id)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
            .order_by(Interview.scheduled_at)
        )
        return list(self._session.execute(stmt).all())