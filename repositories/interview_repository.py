"""مستودع المقابلات: استعلامات خاصة بجدول interviews."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.interview import Interview
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
