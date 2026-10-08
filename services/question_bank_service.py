"""خدمة أسئلة المقابلة: كل سؤال تابع لمقابلة واحدة (مرشح + وظيفة + تاريخ). إضافة/تعديل/حذف يدوي، توليد
بالذكاء الاصطناعي، واستيراد اختياري لأسئلة مقابلة أخرى (نص فقط، بدون إجابات) للمقارنة بين المرشحين.
أوزان الكفاءات تبقى على مستوى الوظيفة."""

import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.constants import QUESTION_DIFFICULTIES, QUESTION_TYPES
from core.exceptions import ValidationError
from core.logging import get_logger
from models.application import Application
from models.candidate import Candidate
from models.interview import Interview
from models.interview_answer import InterviewAnswer
from models.job import Job
from models.job_question import JobQuestion
from repositories.job_question_repository import JobQuestionRepository

logger = get_logger(__name__)

_CATEGORY_LABELS = {
    "cv_specific": "خاص بالسيرة الذاتية",
    "technical": "تقني",
    "behavioral": "سلوكي",
    "leadership": "قيادي",
}
_UPDATABLE_EXTRAS = {"competency", "difficulty", "question_type", "options"}


def split_questions(raw: str) -> list[str]:
    parts = re.split(r"[\n؟?]+", raw or "")
    return [p.strip() for p in parts if p.strip()]


def split_options(raw: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,،\n]", raw or "") if p.strip()]


def _norm(text: str) -> str:
    """صيغة مقارنة للسؤال (لمطابقة نفس السؤال بين مقابلات مختلفة)."""
    return " ".join((text or "").lower().split())


class QuestionBankService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._questions = JobQuestionRepository(session)

    # ------------------------------------------------------------ قراءة

    def list_for_interview(self, interview_id: int) -> list[JobQuestion]:
        return self._questions.get_for_interview(interview_id)

    def as_text(self, interview_id: int) -> str:
        return "\n".join(q.question for q in self.list_for_interview(interview_id))

    def _job_id_of(self, interview_id: int) -> int:
        interview = self._session.get(Interview, interview_id)
        application = self._session.get(Application, interview.application_id) if interview else None
        if application is None:
            raise ValidationError("المقابلة غير موجودة.")
        return application.job_id

    # ------------------------------------------------------------ إضافة / تعديل / حذف

    def add_question(
        self, interview_id: int, text: str, *, question_type: str = "text", options: list[str] | None = None,
        competency: str | None = None, difficulty: str | None = None,
        category: str | None = None, rationale: str | None = None, source: str = "manual",
        imported_from: int | None = None,
    ) -> JobQuestion:
        text = (text or "").strip()
        if not text:
            raise ValidationError("نص السؤال مطلوب.")
        self._validate_extras(question_type, options, difficulty)
        question = JobQuestion(
            job_id=self._job_id_of(interview_id), interview_id=interview_id, question=text,
            question_type=question_type, options=options or None,
            competency=(competency or "").strip() or None, difficulty=difficulty or None,
            category=category, rationale=rationale, source=source, imported_from_interview_id=imported_from,
        )
        self._questions.add(question)
        return question

    @staticmethod
    def _validate_extras(question_type: str | None, options: list[str] | None, difficulty: str | None) -> None:
        if question_type is not None and question_type not in QUESTION_TYPES:
            raise ValidationError(f"نوع سؤال غير صالح: {question_type}")
        if question_type == "choice" and len(options or []) < 2:
            raise ValidationError("سؤال الاختيار من متعدد يحتاج خيارين على الأقل.")
        if difficulty and difficulty not in QUESTION_DIFFICULTIES:
            raise ValidationError(f"مستوى صعوبة غير صالح: {difficulty}")

    def sync_bulk_text(self, interview_id: int, raw_text: str) -> dict:
        """يزامن أسئلة المقابلة مع نص textarea (سؤال لكل سطر). يرجع {updated, added, removed}."""
        lines = split_questions(raw_text)
        existing = self.list_for_interview(interview_id)
        common = min(len(existing), len(lines))

        updated = 0
        for i in range(common):
            if existing[i].question != lines[i]:
                existing[i].question = lines[i]
                updated += 1

        job_id = self._job_id_of(interview_id)
        for text in lines[common:]:
            self._questions.add(JobQuestion(job_id=job_id, interview_id=interview_id, question=text, source="manual"))

        removed = existing[common:]
        if removed:
            self._session.execute(
                delete(InterviewAnswer).where(InterviewAnswer.question_id.in_([q.id for q in removed]))
            )
            for q in removed:
                self._questions.delete(q)
        return {"updated": updated, "added": len(lines) - common if len(lines) > common else 0,
                "removed": len(removed)}

    def add_ai_questions(self, interview_id: int, result) -> list[JobQuestion]:
        """يضيف أسئلة مولّدة بالذكاء الاصطناعي (InterviewQuestions) إلى هذه المقابلة فقط."""
        job_id = self._job_id_of(interview_id)
        sections = [
            ("cv_specific", result.cv_specific), ("technical", result.technical),
            ("behavioral", result.behavioral), ("leadership", result.leadership),
        ]
        created = []
        for category, items in sections:
            for item in items:
                question = JobQuestion(
                    job_id=job_id, interview_id=interview_id, question=item.question, category=category,
                    rationale=item.rationale, source="ai", question_type="text",
                    competency=item.competency, difficulty=item.difficulty,
                )
                self._questions.add(question)
                created.append(question)
        return created

    def update_question(self, question_id: int, text: str, **extras) -> JobQuestion:
        question = self._get_or_raise(question_id)
        text = (text or "").strip()
        if not text:
            raise ValidationError("نص السؤال مطلوب.")
        unknown = set(extras) - _UPDATABLE_EXTRAS
        if unknown:
            raise ValidationError(f"حقول غير قابلة للتعديل: {', '.join(sorted(unknown))}")
        self._validate_extras(
            extras.get("question_type", question.question_type),
            extras.get("options", question.options),
            extras.get("difficulty"),
        )
        question.question = text
        for name, value in extras.items():
            if name == "competency":
                value = (value or "").strip() or None
            setattr(question, name, value or None)
        return question

    def delete_question(self, question_id: int) -> None:
        question = self._get_or_raise(question_id)
        self._session.execute(delete(InterviewAnswer).where(InterviewAnswer.question_id == question_id))
        self._questions.delete(question)

    def delete_for_interview(self, interview_id: int) -> None:
        """حذف كل أسئلة المقابلة وإجاباتها (عند حذف المقابلة)."""
        ids = [q.id for q in self.list_for_interview(interview_id)]
        if ids:
            self._session.execute(delete(InterviewAnswer).where(InterviewAnswer.question_id.in_(ids)))
        self._questions.delete_for_interview(interview_id)

    def _get_or_raise(self, question_id: int) -> JobQuestion:
        question = self._questions.get_by_id(question_id)
        if question is None:
            raise ValidationError("السؤال غير موجود.")
        return question

    # ------------------------------------------------------------ استيراد ومقارنة (اختياري)

    def importable_interviews(self, interview_id: int, same_job_only: bool = True) -> list[dict]:
        """مقابلات أخرى لها أسئلة يمكن استيرادها، الأحدث أولاً (افتراضياً لنفس الوظيفة)."""
        job_id = self._job_id_of(interview_id)
        stmt = (
            select(Interview, Candidate.full_name, Application.job_id)
            .join(Application, Application.id == Interview.application_id)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .where(Interview.id != interview_id)
            .order_by(Interview.scheduled_at.desc())
        )
        if same_job_only:
            stmt = stmt.where(Application.job_id == job_id)
        rows = []
        for interview, name, _ in self._session.execute(stmt).all():
            count = len(self.list_for_interview(interview.id))
            if not count:
                continue
            when = interview.scheduled_at.strftime("%Y-%m-%d") if interview.scheduled_at else "-"
            rows.append({
                "id": interview.id, "count": count,
                "label": f"{interview.code or f'#{interview.id}'} · {name} · {when} · {count} سؤال",
            })
        return rows

    def import_from_interview(self, target_id: int, source_id: int) -> int:
        """ينسخ نص أسئلة مقابلة أخرى (بدون إجابات) متخطياً المكرر. يرجع عدد المنسوخ."""
        if target_id == source_id:
            raise ValidationError("اختر مقابلة مختلفة للاستيراد منها.")
        job_id = self._job_id_of(target_id)
        existing = {_norm(q.question) for q in self.list_for_interview(target_id)}
        copied = 0
        for q in self.list_for_interview(source_id):
            if _norm(q.question) in existing:
                continue
            self._questions.add(JobQuestion(
                job_id=job_id, interview_id=target_id, question=q.question, category=q.category,
                rationale=q.rationale, source=q.source, question_type=q.question_type, options=q.options,
                competency=q.competency, difficulty=q.difficulty, imported_from_interview_id=source_id,
            ))
            copied += 1
        return copied

    def compare(self, interview_ids: list[int]) -> list[dict]:
        """الأسئلة المتطابقة النص بين مقابلتين فأكثر مع الدرجة الفعلية لكل مقابلة: [{question, scores{id: درجة}}]."""
        rows: dict[str, dict] = {}
        for iid in interview_ids:
            answers = {
                a.question_id: a for a in self._session.scalars(
                    select(InterviewAnswer).where(InterviewAnswer.interview_id == iid)
                )
            }
            for q in self.list_for_interview(iid):
                row = rows.setdefault(_norm(q.question), {"question": q.question, "scores": {}})
                answer = answers.get(q.id)
                row["scores"][iid] = answer.eval_score if answer else None
        return [r for r in rows.values() if len(r["scores"]) >= 2]

    # ------------------------------------------------------------ أوزان الكفاءات (على مستوى الوظيفة)

    def competency_weights_text(self, job_id: int) -> str:
        job = self._session.get(Job, job_id)
        weights = (job.competency_weights if job else None) or {}
        return "\n".join(f"{name}: {value:g}" for name, value in weights.items())

    def set_competency_weights(self, job_id: int, raw_text: str) -> dict[str, float]:
        job = self._session.get(Job, job_id)
        if job is None:
            raise ValidationError("الوظيفة غير موجودة.")
        weights: dict[str, float] = {}
        for line in (raw_text or "").splitlines():
            if not line.strip():
                continue
            parts = re.split(r"\s*[:=：]\s*", line.strip(), maxsplit=1)
            if len(parts) != 2 or not parts[0].strip():
                raise ValidationError(f"سطر غير صالح (الصيغة: الاسم: الوزن): {line}")
            try:
                weight = float(parts[1])
            except ValueError:
                raise ValidationError(f"وزن غير صالح في السطر: {line}") from None
            if weight < 0:
                raise ValidationError(f"الوزن لا يمكن أن يكون سالباً: {line}")
            weights[parts[0].strip()] = weight
        job.competency_weights = weights
        return weights

    @staticmethod
    def category_label(category: str | None) -> str:
        return _CATEGORY_LABELS.get(category or "", "") if category else "يدوي"


def migrate_legacy_bank(session: Session) -> int:
    """
    ترحيل لمرة واحدة: كل سؤال قديم في بنك وظيفة (interview_id = NULL) يُنسخ إلى كل مقابلة قائمة لتلك الوظيفة،
    وتُعاد إجابات المقابلة إلى نسختها، ثم تُحذف الأسئلة القديمة. يرجع عدد الأسئلة المنسوخة.
    تنبيه: أسئلة وظيفة لا توجد لها أي مقابلة تُحذف أيضاً (لأن الأسئلة لم تعد تُحفظ إلا داخل مقابلة).
    """
    legacy = list(session.scalars(select(JobQuestion).where(JobQuestion.interview_id.is_(None))))
    if not legacy:
        return 0
    by_job: dict[int, list[JobQuestion]] = {}
    for q in legacy:
        by_job.setdefault(q.job_id, []).append(q)

    copied = 0
    rows = session.execute(
        select(Interview.id, Application.job_id).join(Application, Application.id == Interview.application_id)
    ).all()
    for interview_id, job_id in rows:
        mapping: dict[int, int] = {}
        for q in by_job.get(job_id, []):
            clone = JobQuestion(
                job_id=job_id, interview_id=interview_id, question=q.question, category=q.category,
                rationale=q.rationale, source=q.source, question_type=q.question_type, options=q.options,
                competency=q.competency, difficulty=q.difficulty,
            )
            session.add(clone)
            session.flush()
            mapping[q.id] = clone.id
            copied += 1
        for answer in session.scalars(select(InterviewAnswer).where(InterviewAnswer.interview_id == interview_id)):
            if answer.question_id in mapping:
                answer.question_id = mapping[answer.question_id]
    session.flush()
    session.execute(delete(JobQuestion).where(JobQuestion.interview_id.is_(None)))
    logger.info("Legacy question bank migrated: %s question(s) copied into interviews", copied)
    return copied