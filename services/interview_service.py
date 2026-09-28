"""خدمة المقابلات: جدولة المقابلات، إدارة إجابات المرشح، تقييم الذكاء الاصطناعي وتقييم المُقابِل
(منفصلان)، استيراد الإجابات من Word، تقييم الكفاءات، والدرجة النهائية. القرار النهائي بشري فقط."""

from collections.abc import Callable
from datetime import date

from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.constants import INTERVIEW_DECISIONS, INTERVIEW_STATUSES, INTERVIEW_TYPES
from core.exceptions import SmartATSError, ValidationError
from core.logging import get_logger
from models.interview import Interview
from models.interview_answer import InterviewAnswer
from models.job import Job
from repositories.application_repository import ApplicationRepository
from repositories.interview_answer_repository import InterviewAnswerRepository
from repositories.interview_repository import InterviewRepository
from repositories.job_question_repository import JobQuestionRepository

logger = get_logger(__name__)

_EDITABLE_FIELDS = {
    "interview_type", "status", "scheduled_at", "interviewer", "location",
    "questions", "notes", "feedback", "evaluation", "next_action", "decision",
}

_MAX_ANSWER_SCORE = 5
_OVERALL_SCALE = 100 / _MAX_ANSWER_SCORE  # تحويل متوسط (من 5) إلى درجة من 100
_MAX_PRIOR_ANSWER_CHARS = 800  # اقتطاع كل إجابة سابقة في السياق حتى لا يتضخم الـ prompt
_AI_DIMENSIONS = ("technical_knowledge", "problem_solving", "communication", "practical_experience")

AUTO, MANUAL = "auto", "manual"


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
        decision = fields.get("decision")
        if decision is not None and decision not in INTERVIEW_DECISIONS:
            raise ValidationError(f"قرار غير صالح: {decision}")
        evaluation = fields.get("evaluation")
        if evaluation is not None and not (1 <= evaluation <= 5):
            raise ValidationError("التقييم يجب أن يكون بين 1 و5.")

    def schedule(self, application_id: int, **fields) -> Interview:
        if self._applications.get_by_id(application_id) is None:
            raise ValidationError("التقديم غير موجود.")
        self._validate_fields(fields)
        interview = Interview(application_id=application_id, **fields)
        self._interviews.add(interview)  # add() يعمل flush فيتوفر id
        interview.code = f"INT-{date.today().year}-{interview.id:04d}"
        logger.info("Interview %s scheduled for application %s", interview.code, application_id)
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

    def history_for_candidate(self, candidate_id: int, exclude_id: int | None = None) -> list[dict]:
        """مقابلات المرشح السابقة (كل الوظائف) لتجنب تكرار الأسئلة وفهم مساره."""
        return [
            {
                "date": iv.scheduled_at.strftime("%Y-%m-%d") if iv.scheduled_at else "-",
                "type": iv.interview_type,
                "job": job.title,
                "interviewer": iv.interviewer or "-",
                "score": iv.overall_score,
            }
            for iv, job in self._interviews.list_for_candidate(candidate_id)
            if iv.id != exclude_id
        ]

    # ------------------------------------------------------------ إجابات المرشح وتقييمها

    def answers_map(self, interview_id: int) -> dict[int, InterviewAnswer]:
        """إجابات هذه المقابلة كـ dict مفتاحه question_id، لدمجها مع بنك أسئلة الوظيفة عند العرض."""
        return {a.question_id: a for a in self._answers.get_for_interview(interview_id)}

    @staticmethod
    def _backfill_legacy(answer: InterviewAnswer) -> None:
        """سجلات ما قبل الفصل بين تقييم AI والمُقابِل: ننقل eval_score إلى الحقل الصحيح مرة واحدة."""
        if answer.eval_score is None or answer.ai_score is not None or answer.manual_score is not None:
            return
        if answer.eval_method == "manual":
            answer.manual_score = answer.eval_score
        else:
            answer.ai_score = answer.eval_score

    @staticmethod
    def _sync_effective(answer: InterviewAnswer) -> None:
        """الدرجة الفعلية = تقييم المُقابِل إن وُجد، وإلا تقييم الذكاء الاصطناعي."""
        if answer.manual_score:
            answer.eval_score, answer.eval_method = answer.manual_score, "manual"
        elif answer.ai_score:
            answer.eval_score, answer.eval_method = answer.ai_score, "ai"
        else:
            answer.eval_score, answer.eval_method = None, None

    def _get_or_create_answer(self, interview_id: int, question_id: int) -> InterviewAnswer:
        answer = self._answers.get_one(interview_id, question_id)
        if answer is None:
            if self._job_questions.get_by_id(question_id) is None:
                raise ValidationError("السؤال غير موجود.")
            answer = InterviewAnswer(interview_id=interview_id, question_id=question_id)
            self._answers.add(answer)
        else:
            self._backfill_legacy(answer)
        return answer

    def save_answer(self, interview_id: int, question_id: int, text: str) -> InterviewAnswer:
        answer = self._get_or_create_answer(interview_id, question_id)
        answer.answer = (text or "").strip() or None
        return answer

    def _prior_qa(self, interview_id: int, question_id: int) -> list[tuple[str, str]]:
        """(سؤال، إجابة) لبقية إجابات المقابلة، كسياق مرجعي فقط عند تقييم سؤال."""
        pairs: list[tuple[str, str]] = []
        for other_id, other in self.answers_map(interview_id).items():
            text = (other.answer or "").strip()
            if other_id == question_id or not text:
                continue
            question = self._job_questions.get_by_id(other_id)
            if question is not None:
                pairs.append((question.question, text[:_MAX_PRIOR_ANSWER_CHARS]))
        return pairs

    def evaluate_answer(self, interview_id: int, question_id: int, job) -> InterviewAnswer:
        """
        تحليل بالذكاء الاصطناعي: يكتب حقول ai_* فقط ولا يمسّ تقييم المُقابِل. الدرجة الفعلية
        تبقى درجة المُقابِل إن كان قد قيّم السؤال.
        """
        answer = self._get_or_create_answer(interview_id, question_id)
        if not (answer.answer or "").strip():
            raise ValidationError("أدخل إجابة المرشح أولاً.")

        question = self._job_questions.get_by_id(question_id)
        from ai.interview_generator import evaluate_interview_answer

        evaluation = evaluate_interview_answer(
            job, question.question, answer.answer, self._prior_qa(interview_id, question_id)
        )
        answer.ai_score = evaluation.score
        answer.ai_dimensions = {
            name: getattr(evaluation, name) for name in _AI_DIMENSIONS if getattr(evaluation, name) is not None
        }
        answer.ai_followup = (evaluation.follow_up_question or "").strip() or None
        answer.eval_feedback = evaluation.feedback
        answer.eval_strengths = evaluation.strengths
        answer.eval_concerns = evaluation.concerns
        self._sync_effective(answer)
        return answer

    def set_interviewer_review(
        self, interview_id: int, question_id: int, score: int | None, notes: str | None
    ) -> InterviewAnswer:
        """تقييم المُقابِل (1-5 أو None لإلغائه) وملاحظاته على إجابة واحدة."""
        if score is not None and not (1 <= score <= _MAX_ANSWER_SCORE):
            raise ValidationError("التقييم يجب أن يكون بين 1 و5.")
        answer = self._get_or_create_answer(interview_id, question_id)
        answer.manual_score = score
        answer.interviewer_notes = (notes or "").strip() or None
        self._sync_effective(answer)
        return answer

    # ------------------------------------------------------------ استيراد الإجابات من Word

    def import_answers(
        self,
        interview_id: int,
        job,
        answers_by_question: dict[int, str],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> dict:
        """
        يحفظ الإجابات المستوردة ثم يقيّم كل واحدة بالذكاء الاصطناعي، ثم يحسب الدرجة النهائية.
        تُحفظ كل الإجابات أولاً ثم تُقيَّم ليرى كل تقييم بقية الإجابات كسياق. فشل تقييم سؤال
        واحد لا يوقف الباقي. يرجع: {"saved","evaluated","failed","unknown","overall_score"}.
        """
        self._get_or_raise(interview_id)
        valid_ids = {q.id for q in self._job_questions.get_for_job(job.id)}

        unknown = [qid for qid in answers_by_question if qid not in valid_ids]
        to_import = {qid: text for qid, text in answers_by_question.items() if qid in valid_ids}

        for question_id, text in to_import.items():
            self.save_answer(interview_id, question_id, text)
        self._session.flush()  # الجلسة بدون autoflush؛ نحتاج الإجابات مرئية للاستعلام داخل _prior_qa

        evaluated, failed = 0, []
        total = len(to_import)
        for done, question_id in enumerate(to_import, start=1):
            try:
                self.evaluate_answer(interview_id, question_id, job)
                evaluated += 1
            except SmartATSError as exc:
                logger.warning("Evaluation failed for question %s: %s", question_id, exc)
                failed.append((question_id, str(exc)))
            if on_progress:
                on_progress(done, total)

        overall = self.finalize_score(interview_id, respect_manual=True) if to_import else None
        return {
            "saved": total, "evaluated": evaluated, "failed": failed,
            "unknown": unknown, "overall_score": overall,
        }

    # ------------------------------------------------------------ الكفاءات والدرجة النهائية

    def competency_report(self, interview_id: int, job) -> dict:
        """
        درجة كل كفاءة (من 100) = متوسط الدرجات الفعلية لأسئلتها المجابة × 20.
        overall = متوسط مرجّح بأوزان الوظيفة على الكفاءات المُقيَّمة فقط (بدون أوزان: متوسط بسيط).
        يرجع {"scores": {name: value}, "overall": float | None}.
        """
        answers = self.answers_map(interview_id)
        buckets: dict[str, list[int]] = {}
        for question in self._job_questions.get_for_job(job.id):
            name = (question.competency or "").strip()
            answer = answers.get(question.id)
            if name and answer is not None and answer.eval_score is not None:
                buckets.setdefault(name, []).append(answer.eval_score)

        scores = {name: round(sum(v) / len(v) * _OVERALL_SCALE, 1) for name, v in buckets.items()}
        if not scores:
            return {"scores": {}, "overall": None}

        configured = job.competency_weights or {}
        weights = {name: float(configured.get(name) or 0) for name in scores}
        if sum(weights.values()) <= 0:
            weights = {name: 1.0 for name in scores}
        overall = sum(scores[n] * weights[n] for n in scores) / sum(weights.values())
        return {"scores": scores, "overall": round(overall, 1)}

    def finalize_score(self, interview_id: int, *, respect_manual: bool = False) -> float | None:
        """
        الدرجة النهائية (من 100): متوسط الكفاءات المرجّح إن حدّدت الوظيفة أوزاناً وأُجيب على أسئلة
        مربوطة بكفاءات، وإلا متوسط كل الدرجات الفعلية × 20.
        respect_manual=True: لا يستبدل درجة عدّلها المُقابِل يدوياً (يُستخدم عند الاستيراد التلقائي).
        """
        interview = self._get_or_raise(interview_id)
        if respect_manual and interview.overall_method == MANUAL and interview.overall_score is not None:
            return interview.overall_score

        overall = None
        application = self._applications.get_by_id(interview.application_id)
        job = self._session.get(Job, application.job_id) if application else None
        if job is not None and job.competency_weights:
            overall = self.competency_report(interview_id, job)["overall"]

        if overall is None:
            scores = [
                a.eval_score for a in self._answers.get_for_interview(interview_id) if a.eval_score is not None
            ]
            if not scores:
                return None
            overall = round(sum(scores) / len(scores) * _OVERALL_SCALE, 1)

        interview.overall_score = overall
        interview.overall_method = AUTO
        return interview.overall_score

    def set_overall(
        self, interview_id: int, score: float | None, notes: str | None, decision: str | None = None
    ) -> Interview:
        """
        تعديل بشري للتقييم النهائي: score=None يبقي الدرجة كما هي، decision=None يبقي القرار كما هو.
        الدرجة المعدّلة تُوسَم "manual" فلا يستبدلها الاستيراد التلقائي لاحقاً.
        """
        interview = self._get_or_raise(interview_id)
        if score is not None:
            if not (0 <= score <= 100):
                raise ValidationError("الدرجة النهائية يجب أن تكون بين 0 و100.")
            interview.overall_score = round(float(score), 1)
            interview.overall_method = MANUAL
        if decision is not None:
            if decision not in INTERVIEW_DECISIONS:
                raise ValidationError(f"قرار غير صالح: {decision}")
            interview.decision = decision
        interview.overall_notes = (notes or "").strip() or None
        return interview

    def answered_stats(self, interview_id: int) -> tuple[int, int]:
        """(عدد الإجابات المقيَّمة، عدد الإجابات المكتوبة) لعرضها بجانب الدرجة النهائية."""
        answers = self._answers.get_for_interview(interview_id)
        written = [a for a in answers if (a.answer or "").strip()]
        scored = [a for a in answers if a.eval_score is not None]
        return len(scored), len(written)