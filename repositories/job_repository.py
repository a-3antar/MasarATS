"""مستودع الوظائف: استعلامات خاصة بجدول jobs."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models.job import Job
from repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Job)

    def list_open(self) -> list[Job]:
        stmt = select(Job).where(Job.status == "Open")
        return list(self._session.scalars(stmt).all())

    def list_for_position(self, position_id: int) -> list[Job]:
        """كل الوظائف المرتبطة بمسمى وظيفي في الهيكل التنظيمي، الأحدث أولاً."""
        stmt = select(Job).where(Job.position_id == position_id).order_by(Job.created_at.desc())
        return list(self._session.scalars(stmt).all())

    def search(self, query: str, limit: int = 200) -> list[Job]:
        """بحث نصي بالمسمى أو القسم أو الموقع."""
        like = f"%{query}%"
        stmt = (
            select(Job)
            .where(or_(Job.title.ilike(like), Job.department.ilike(like), Job.location.ilike(like)))
            .limit(limit)
        )
        return list(self._session.scalars(stmt).all())