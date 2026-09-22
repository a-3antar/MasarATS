"""خدمة التقديمات: تغيير مرحلة التقديم في خط التوظيف ومزامنة حالة المرشح العامة معها."""

from sqlalchemy.orm import Session

from core.constants import APPLICATION_STATUSES
from core.exceptions import ValidationError
from core.logging import get_logger
from models.application import Application
from repositories.application_repository import ApplicationRepository
from repositories.candidate_repository import CandidateRepository

logger = get_logger(__name__)

_NEW = APPLICATION_STATUSES[0]
_REJECTED = APPLICATION_STATUSES[-1]
_ACTIVE_ORDER = [s for s in APPLICATION_STATUSES if s not in (_NEW, _REJECTED)]


class ApplicationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._applications = ApplicationRepository(session)
        self._candidates = CandidateRepository(session)

    def change_status(self, application_id: int, new_status: str) -> Application:
        """يغيّر مرحلة تقديم واحد ثم يعيد حساب حالة المرشح العامة."""
        if new_status not in APPLICATION_STATUSES:
            raise ValidationError(f"مرحلة غير صالحة: {new_status}")

        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ValidationError("التقديم غير موجود.")

        application.status = new_status
        self._session.flush()  # الجلسة بدون autoflush؛ نحتاج التغيير مرئياً قبل إعادة الحساب
        self._sync_candidate_status(application.candidate_id)
        logger.info("Application %s moved to %s", application_id, new_status)
        return application

    def _sync_candidate_status(self, candidate_id: int) -> None:
        candidate = self._candidates.get_by_id(candidate_id)
        if candidate is None:
            return
        statuses = [a.status for a in self._applications.get_for_candidate(candidate_id)]
        candidate.status = self.derive_candidate_status(statuses)

    @staticmethod
    def derive_candidate_status(statuses: list[str]) -> str:
        active = [s for s in statuses if s in _ACTIVE_ORDER]
        if active:
            return max(active, key=_ACTIVE_ORDER.index)
        if statuses and all(s == _REJECTED for s in statuses):
            return _REJECTED
        return _NEW