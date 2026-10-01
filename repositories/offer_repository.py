"""مستودع العروض: استعلامات خاصة بجدول offers."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.constants import ACTIVE_OFFER_STATUSES
from models.application import Application
from models.candidate import Candidate
from models.job import Job
from models.offer import Offer
from repositories.base import BaseRepository


class OfferRepository(BaseRepository[Offer]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Offer)

    def get_active_for_application(self, application_id: int) -> Offer | None:
        stmt = select(Offer).where(
            Offer.application_id == application_id, Offer.status.in_(ACTIVE_OFFER_STATUSES)
        )
        return self._session.scalars(stmt).first()

    def active_application_ids(self) -> set[int]:
        stmt = select(Offer.application_id).where(Offer.status.in_(ACTIVE_OFFER_STATUSES))
        return set(self._session.scalars(stmt).all())

    def list_with_context(self) -> list[tuple[Offer, Application, Candidate, Job]]:
        stmt = (
            select(Offer, Application, Candidate, Job)
            .join(Application, Application.id == Offer.application_id)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
            .order_by(Offer.created_at.desc())
        )
        return [tuple(row) for row in self._session.execute(stmt).all()]
