"""خدمة التقديمات: تغيير المرحلة (مع تسجيل التاريخ)، مزامنة حالة المرشح، وتحديث current_headcount عند التعيين."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.constants import APPLICATION_STATUSES
from core.exceptions import ValidationError
from core.logging import get_logger
from models.application import Application
from models.application_stage_history import ApplicationStageHistory
from models.candidate import Candidate
from models.job import Job
from models.position import Position
from repositories.application_repository import ApplicationRepository
from repositories.candidate_repository import CandidateRepository

logger = get_logger(__name__)

_NEW = APPLICATION_STATUSES[0]
_HIRED = "Hired"
_REJECTED = APPLICATION_STATUSES[-1]
_ACTIVE_ORDER = [s for s in APPLICATION_STATUSES if s not in (_NEW, _REJECTED)]
_DEFAULT_HISTORY_LIMIT = 100


class ApplicationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._applications = ApplicationRepository(session)
        self._candidates = CandidateRepository(session)

    def change_status(
        self, application_id: int, new_status: str, changed_by: str | None = None, note: str | None = None
    ) -> Application:
        """
        يغيّر مرحلة تقديم واحد ويسجّل الانتقال في application_stage_history،
        ثم يعدّل current_headcount للمسمى المرتبط (عند دخول/خروج Hired)، ثم يعيد حساب حالة المرشح.
        """
        if new_status not in APPLICATION_STATUSES:
            raise ValidationError(f"مرحلة غير صالحة: {new_status}")

        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ValidationError("التقديم غير موجود.")

        old_status = application.status
        if old_status == new_status:
            return application

        application.status = new_status
        self._session.add(ApplicationStageHistory(
            application_id=application_id, from_status=old_status, to_status=new_status,
            changed_by=changed_by, note=(note or "").strip() or None,
        ))
        self._session.flush()  # الجلسة بدون autoflush؛ نحتاج التغيير مرئياً قبل إعادة الحساب
        self._adjust_headcount(application.job_id, old_status, new_status)
        self._sync_candidate_status(application.candidate_id)
        logger.info("Application %s moved %s -> %s by %s", application_id, old_status, new_status, changed_by)
        return application

    def _adjust_headcount(self, job_id: int, old_status: str, new_status: str) -> None:
        """+1 عند الانتقال إلى Hired، و-1 عند الخروج منها (تصحيح خطأ)، على مسمى الوظيفة في الهيكل."""
        delta = int(new_status == _HIRED) - int(old_status == _HIRED)
        if not delta:
            return
        job = self._session.get(Job, job_id)
        position = self._session.get(Position, job.position_id) if job and job.position_id else None
        if position is None:
            logger.info("Hire on job %s has no linked position; headcount not updated", job_id)
            return
        position.current_headcount = max(position.current_headcount + delta, 0)
        
        if position.current_headcount > position.required_headcount:
            logger.warning("Position %s headcount %s exceeds required %s",
                           position.id, position.current_headcount, position.required_headcount)

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

    def recent_history(self, limit: int = _DEFAULT_HISTORY_LIMIT) -> list[dict]:
        """آخر انتقالات المراحل عبر كل التقديمات، الأحدث أولاً."""
        stmt = (
            select(ApplicationStageHistory, Candidate.full_name, Job.title)
            .join(Application, Application.id == ApplicationStageHistory.application_id)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
            .order_by(ApplicationStageHistory.changed_at.desc(), ApplicationStageHistory.id.desc())
            .limit(limit)
        )
        return [
            {"at": h.changed_at, "candidate": name, "job": title, "from": h.from_status,
             "to": h.to_status, "by": h.changed_by, "note": h.note}
            for h, name, title in self._session.execute(stmt).all()
        ]
