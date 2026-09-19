"""مستودع التقديمات: استعلامات خاصة بجدول applications."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.application import Application
from repositories.base import BaseRepository


class ApplicationRepository(BaseRepository[Application]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Application)

    def get_for_job(self, job_id: int) -> list[Application]:
        stmt = (
            select(Application)
            .where(Application.job_id == job_id)
            .order_by(Application.match_score.desc())
        )
        return list(self._session.scalars(stmt).all())

    def get_existing(self, candidate_id: int, job_id: int) -> Application | None:
        stmt = select(Application).where(
            Application.candidate_id == candidate_id, Application.job_id == job_id
        )
        return self._session.scalars(stmt).first()
