"""خدمة المقابلات: جدولة المقابلات ضمن تقديم مرشح على وظيفة، وتسجيل نتائجها."""

from sqlalchemy.orm import Session

from core.constants import INTERVIEW_STATUSES, INTERVIEW_TYPES
from core.exceptions import ValidationError
from core.logging import get_logger
from models.interview import Interview
from repositories.application_repository import ApplicationRepository
from repositories.interview_repository import InterviewRepository

logger = get_logger(__name__)

_EDITABLE_FIELDS = {
    "interview_type", "status", "scheduled_at", "interviewer", "location",
    "questions", "notes", "feedback", "evaluation", "next_action",
}


class InterviewService:
    def __init__(self, session: Session) -> None:
        self._interviews = InterviewRepository(session)
        self._applications = ApplicationRepository(session)

    @staticmethod
    def _validate_fields(fields: dict) -> None:
        unknown = set(fields) - _EDITABLE_FIELDS
        if unknown:
            raise ValidationError(f"حقول غير قابلة للتعديل: {', '.join(sorted(unknown))}")
        itype = fields.get("interview_type")
        if itype is not None and itype not in INTERVIEW_TYPES:
            raise ValidationError(f"نوع مقابلة غير صالح: {itype}")
        status = fields.get("status")
        if status is not None and status not in INTERVIEW_STATUSES:
            raise ValidationError(f"حالة مقابلة غير صالحة: {status}")
        evaluation = fields.get("evaluation")
        if evaluation is not None and not (1 <= evaluation <= 5):
            raise ValidationError("التقييم يجب أن يكون بين 1 و5.")

    def schedule(self, application_id: int, **fields) -> Interview:
        if self._applications.get_by_id(application_id) is None:
            raise ValidationError("التقديم غير موجود.")
        self._validate_fields(fields)
        interview = Interview(application_id=application_id, **fields)
        self._interviews.add(interview)
        logger.info("Interview scheduled for application %s", application_id)
        return interview

    def update(self, interview_id: int, **fields) -> Interview:
        interview = self._get_or_raise(interview_id)
        self._validate_fields(fields)
        for name, value in fields.items():
            setattr(interview, name, value)
        return interview

    def delete(self, interview_id: int) -> None:
        interview = self._get_or_raise(interview_id)
        self._interviews.delete(interview)

    def _get_or_raise(self, interview_id: int) -> Interview:
        interview = self._interviews.get_by_id(interview_id)
        if interview is None:
            raise ValidationError("المقابلة غير موجودة.")
        return interview

    def list_for_application(self, application_id: int) -> list[Interview]:
        return self._interviews.get_for_application(application_id)

