"""مستودع التقديمات: استعلامات خاصة بجدول applications."""

from sqlalchemy import delete, select, func
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

    def delete_for_job(self, job_id: int) -> None:
        """حذف كل التقديمات المرتبطة بوظيفة (قبل حذف الوظيفة نفسها)."""
        self._session.execute(delete(Application).where(Application.job_id == job_id))

    def get_for_candidate(self, candidate_id: int) -> list[Application]:
        stmt = select(Application).where(Application.candidate_id == candidate_id)
        return list(self._session.scalars(stmt).all())

    def summary_by_candidate(self) -> dict[int, dict]:
        """أفضل درجة مطابقة وعدد التقديمات لكل مرشح - استعلام واحد لكل المرشحين."""
        stmt = select(
            Application.candidate_id, func.max(Application.match_score), func.count()
        ).group_by(Application.candidate_id)
        return {
            cid: {"best": best, "apps": total}
            for cid, best, total in self._session.execute(stmt).all()
        }