"""خدمة المقابلات: جدولة المقابلات، وإدارة إجابات المرشح على بنك أسئلة الوظيفة وتقييمها."""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.constants import INTERVIEW_STATUSES, INTERVIEW_TYPES
from core.exceptions import ValidationError
from core.logging import get_logger
from models.interview import Interview
from models.interview_answer import InterviewAnswer
from repositories.application_repository import ApplicationRepository
from repositories.interview_answer_repository import InterviewAnswerRepository
from repositories.interview_repository import InterviewRepository
from repositories.job_question_repository import JobQuestionRepository

logger = get_logger(__name__)

_EDITABLE_FIELDS = {
    "interview_type", "status", "scheduled_at", "interviewer", "location",
    "questions", "notes", "feedback", "evaluation", "next_action",
}


class InterviewService:
    def __init__(self, session: Session) -> None:
        self._interviews = InterviewRepository(session)
        self._applications = ApplicationRepository(session)
        self._answers = InterviewAnswerRepository(session)
        self._job_questions = JobQuestionRepository(session)
        self._session = session

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
        self._session.execute(delete(InterviewAnswer).where(InterviewAnswer.interview_id == interview_id))
        self._interviews.delete(interview)

    def _get_or_raise(self, interview_id: int) -> Interview:
        interview = self._interviews.get_by_id(interview_id)
        if interview is None:
            raise ValidationError("المقابلة غير موجودة.")
        return interview

    def get_by_id(self, interview_id: int) -> Interview | None:
        return self._interviews.get_by_id(interview_id)

    def list_for_application(self, application_id: int) -> list[Interview]:
        return self._interviews.get_for_application(application_id)

    def list_all_with_context(self):
        """كل المقابلات مع المرشح والوظيفة المرتبطين بها - لعرض التقويم الموحّد."""
        return self._interviews.list_all_with_context()

    # ------------------------------------------------------------ إجابات المرشح وتقييمها

    def answers_map(self, interview_id: int) -> dict[int, InterviewAnswer]:
        """إجابات هذه المقابلة كـ dict مفتاحه question_id، لدمجها مع بنك أسئلة الوظيفة عند العرض."""
        return {a.question_id: a for a in self._answers.get_for_interview(interview_id)}

    def _get_or_create_answer(self, interview_id: int, question_id: int) -> InterviewAnswer:
        answer = self._answers.get_one(interview_id, question_id)
        if answer is None:
            if self._job_questions.get_by_id(question_id) is None:
                raise ValidationError("السؤال غير موجود.")
            answer = InterviewAnswer(interview_id=interview_id, question_id=question_id)
            self._answers.add(answer)
        return answer

    def save_answer(self, interview_id: int, question_id: int, text: str) -> InterviewAnswer:
        answer = self._get_or_create_answer(interview_id, question_id)
        answer.answer = (text or "").strip() or None
        return answer

    def evaluate_answer(self, interview_id: int, question_id: int, job) -> InterviewAnswer:
        """يقيّم إجابة المرشح على سؤال محدد بالذكاء الاصطناعي بناءً على متطلبات الوظيفة."""
        answer = self._get_or_create_answer(interview_id, question_id)
        if not (answer.answer or "").strip():
            raise ValidationError("أدخل إجابة المرشح أولاً.")

        question = self._job_questions.get_by_id(question_id)
        from ai.interview_generator import evaluate_interview_answer

        evaluation = evaluate_interview_answer(job, question.question, answer.answer)
        answer.eval_score = evaluation.score
        answer.eval_method = "ai"
        answer.eval_feedback = evaluation.feedback
        answer.eval_strengths = evaluation.strengths
        answer.eval_concerns = evaluation.concerns
        return answer

    def set_manual_score(self, interview_id: int, question_id: int, score: int | None) -> InterviewAnswer:
        answer = self._get_or_create_answer(interview_id, question_id)
        if score is not None and not (1 <= score <= 5):
            raise ValidationError("التقييم يجب أن يكون بين 1 و5.")
        answer.eval_score = score
        answer.eval_method = "manual" if score else None
        if score:
            answer.eval_feedback, answer.eval_strengths, answer.eval_concerns = None, [], []
        return answer
