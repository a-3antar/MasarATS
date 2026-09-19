"""مستودع الوظائف: استعلامات خاصة بجدول jobs."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.job import Job
from repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Job)

    def list_open(self) -> list[Job]:
        stmt = select(Job).where(Job.status == "Open")
        return list(self._session.scalars(stmt).all())
