"""خدمة العروض والتعيين. القرار بشري دائماً: قبول العرض لا يعيّن تلقائياً، والتعيين خطوة منفصلة مؤكَّدة."""

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.constants import APPLICATION_STATUSES, OFFER_STATUSES
from core.exceptions import ValidationError
from core.logging import get_logger
from models.application import Application
from models.candidate import Candidate
from models.job import Job
from models.offer import Offer
from repositories.application_repository import ApplicationRepository
from repositories.offer_repository import OfferRepository
from services.application_service import ApplicationService

logger = get_logger(__name__)

_DRAFT, _SENT, _ACCEPTED, _DECLINED, _WITHDRAWN = OFFER_STATUSES
_OFFER_STAGE, _HIRED, _REJECTED, _INTERVIEW_STAGE = "Offer", "Hired", "Rejected", "Interview"
_ELIGIBLE_STAGES = ("Shortlisted", _INTERVIEW_STAGE, _OFFER_STAGE)
_TRANSITIONS = {
    _DRAFT: {_SENT, _WITHDRAWN},
    _SENT: {_ACCEPTED, _DECLINED, _WITHDRAWN},
    _ACCEPTED: {_WITHDRAWN},
    _DECLINED: set(),
    _WITHDRAWN: set(),
}
_RESPONDED = {_ACCEPTED, _DECLINED, _WITHDRAWN}
_STAGE_INDEX = {s: i for i, s in enumerate(APPLICATION_STATUSES)}

# حالات للعرض فقط تُشتق من تاريخ الانتهاء (لا تُخزَّن في القاعدة)
EXPIRING_SOON = "ExpiringSoon"
EXPIRED = "Expired"
EXPIRING_SOON_DAYS = 3  # عرض مُرسل ينتهي خلال هذا العدد من الأيام = "ينتهي قريباً"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OfferService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._offers = OfferRepository(session)
        self._applications = ApplicationRepository(session)
        self._app_service = ApplicationService(session)

    # ------------------------------------------------------------ قراءة

    @staticmethod
    def derive_display_status(status: str, expires_at: date | None, today: date | None = None) -> str:
        """الحالة المعروضة: العرض المُرسل يصبح "ينتهي قريباً" أو "منتهي" حسب تاريخ الانتهاء."""
        if status == _SENT and expires_at is not None:
            remaining = (expires_at - (today or date.today())).days
            if remaining < 0:
                return EXPIRED
            if remaining <= EXPIRING_SOON_DAYS:
                return EXPIRING_SOON
        return status

    def eligible_applications(self) -> list[dict]:
        """تقديمات يجوز إصدار عرض لها (قائمة مختصرة/مقابلة/عرض) وليس لها عرض نشط."""
        busy = self._offers.active_application_ids()
        stmt = (
            select(Application, Candidate, Job)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
            .where(Application.status.in_(_ELIGIBLE_STAGES))
            .order_by(Candidate.full_name)
        )
        return [
            {"application_id": a.id, "candidate": c.full_name, "job": j.title, "status": a.status}
            for a, c, j in self._session.execute(stmt).all() if a.id not in busy
        ]

    def list_offers(self) -> list[dict]:
        today = date.today()
        return [
            {
                "id": o.id, "application_id": a.id, "candidate": c.full_name, "email": c.email,
                "job": j.title, "department": j.department, "status": o.status,
                "display_status": self.derive_display_status(o.status, o.expires_at, today),
                "app_status": a.status, "salary": o.salary, "start_date": o.start_date,
                "expires_at": o.expires_at, "notes": o.notes, "sent_at": o.sent_at,
                "responded_at": o.responded_at, "created_at": o.created_at, "created_by": o.created_by,
            }
            for o, a, c, j in self._offers.list_with_context()
        ]

    def interview_stage_count(self) -> int:
        """عدد التقديمات الموجودة حالياً في مرحلة المقابلة (لعرض مسار التوظيف)."""
        stmt = select(func.count()).select_from(Application).where(Application.status == _INTERVIEW_STAGE)
        return self._session.scalar(stmt) or 0

    # ------------------------------------------------------------ كتابة

    @staticmethod
    def _validate_money_and_expiry(salary: float | None, expires_at: date | None, current: date | None) -> None:
        if salary is not None and salary < 0:
            raise ValidationError("الراتب لا يمكن أن يكون سالباً.")
        if expires_at is not None and expires_at != current and expires_at < date.today():
            raise ValidationError("تاريخ انتهاء العرض لا يمكن أن يكون في الماضي.")

    def create_offer(
        self, application_id: int, salary: float | None, start_date: date | None,
        notes: str | None, changed_by: str | None = None, expires_at: date | None = None,
    ) -> Offer:
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ValidationError("التقديم غير موجود.")
        if application.status in (_REJECTED, _HIRED):
            raise ValidationError("لا يمكن إصدار عرض لتقديم مرفوض أو تم تعيينه.")
        self._validate_money_and_expiry(salary, expires_at, None)
        if self._offers.get_active_for_application(application_id):
            raise ValidationError("يوجد عرض نشط لهذا التقديم بالفعل.")

        offer = Offer(
            application_id=application_id, salary=salary or None, start_date=start_date,
            expires_at=expires_at, notes=(notes or "").strip() or None, created_by=changed_by,
        )
        self._offers.add(offer)
        if _STAGE_INDEX[application.status] < _STAGE_INDEX[_OFFER_STAGE]:
            self._app_service.change_status(
                application_id, _OFFER_STAGE, changed_by, note=f"إنشاء عرض #{offer.id}"
            )
        return offer

    def update_offer(
        self, offer_id: int, salary: float | None, start_date: date | None,
        notes: str | None, expires_at: date | None = None,
    ) -> Offer:
        offer = self._get_or_raise(offer_id)
        if offer.status not in (_DRAFT, _SENT):
            raise ValidationError("لا يمكن تعديل عرض بعد الرد عليه أو سحبه.")
        self._validate_money_and_expiry(salary, expires_at, offer.expires_at)
        offer.salary, offer.start_date, offer.expires_at = salary or None, start_date, expires_at
        offer.notes = (notes or "").strip() or None
        return offer

    def set_status(self, offer_id: int, new_status: str) -> Offer:
        offer = self._get_or_raise(offer_id)
        if new_status not in _TRANSITIONS.get(offer.status, set()):
            raise ValidationError(f"لا يمكن نقل العرض من {offer.status} إلى {new_status}.")
        offer.status = new_status
        if new_status == _SENT:
            offer.sent_at = _utcnow()
        if new_status in _RESPONDED:
            offer.responded_at = _utcnow()
        return offer

    def hire(self, offer_id: int, changed_by: str | None = None) -> Application:
        """تعيين المرشح بعد قبول العرض (إجراء بشري صريح). يزيد current_headcount للمسمى المرتبط."""
        offer = self._get_or_raise(offer_id)
        if offer.status != _ACCEPTED:
            raise ValidationError("لا يمكن التعيين قبل قبول المرشح للعرض.")
        return self._app_service.change_status(
            offer.application_id, _HIRED, changed_by, note=f"تعيين بناءً على العرض #{offer.id}"
        )

    def delete_offer(self, offer_id: int) -> None:
        offer = self._get_or_raise(offer_id)
        if offer.status not in (_DRAFT, _WITHDRAWN, _DECLINED):
            raise ValidationError("لا يُحذف إلا عرض مسودة أو مسحوب أو مرفوض.")
        self._offers.delete(offer)

    def _get_or_raise(self, offer_id: int) -> Offer:
        offer = self._offers.get_by_id(offer_id)
        if offer is None:
            raise ValidationError("العرض غير موجود.")
        return offer