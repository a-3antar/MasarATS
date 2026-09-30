"""خدمة بنك أسئلة الوظيفة: إضافة/تعديل/حذف/نسخ أسئلة، توليدها بالذكاء الاصطناعي، وإدارة أوزان الكفاءات.
الأسئلة مرتبطة بالوظيفة (وليس بمرشح) لإعادة استخدامها مع أي مرشح. نسخ أسئلة وظيفة إلى أخرى يعمل كقالب.

التعديل الجماعي (sync_bulk_text) يقارن السطور الجديدة بالأسئلة الحالية حسب الترتيب:
- سطر في نفس الموضع بنص مختلف → تحديث نص نفس السؤال (يحافظ على الإجابات المرتبطة به).
- سطور زائدة في النهاية → أسئلة جديدة. سطور أقل من الموجود → حذف الزائد من النهاية (مع إجاباته)."""

import re

from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.constants import QUESTION_DIFFICULTIES, QUESTION_TYPES
from core.exceptions import ValidationError
from models.interview_answer import InterviewAnswer
from models.job import Job
from models.job_question import JobQuestion
from repositories.job_question_repository import JobQuestionRepository

_CATEGORY_LABELS = {
    "cv_specific": "خاص بالسيرة الذاتية",
    "technical": "تقني",
    "behavioral": "سلوكي",
    "leadership": "قيادي",
}
_UPDATABLE_EXTRAS = {"competency", "difficulty", "question_type", "options"}


def split_questions(raw: str) -> list[str]:
    """يقسّم نصاً حراً إلى أسئلة منفصلة: كل سطر جديد أو علامة استفهام (عربية أو إنجليزية) يفصل بين سؤالين."""
    parts = re.split(r"[\n؟?]+", raw or "")
    return [p.strip() for p in parts if p.strip()]


def split_options(raw: str) -> list[str]:
    """خيارات سؤال الاختيار من متعدد: مفصولة بفاصلة (عربية/إنجليزية) أو سطر جديد."""
    return [p.strip() for p in re.split(r"[,،\n]", raw or "") if p.strip()]


class QuestionBankService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._questions = JobQuestionRepository(session)

    def list_for_job(self, job_id: int) -> list[JobQuestion]:
        return self._questions.get_for_job(job_id)

    def questions_as_text(self, job_id: int) -> str:
        """نص جاهز لعرضه في textarea واحدة: كل سؤال في سطر، بنفس ترتيب البنك."""
        return "\n".join(q.question for q in self.list_for_job(job_id))

    def as_text(self, job_id: int) -> str:
        """اسم مستعار لـ questions_as_text (للتوافق مع استدعاءات موجودة باسم مختلف)."""
        return "\n".join(q.question for q in self.list_for_job(job_id))

    def add_question(
        self, job_id: int, text: str, *, question_type: str = "text", options: list[str] | None = None,
        competency: str | None = None, difficulty: str | None = None,
        category: str | None = None, rationale: str | None = None, source: str = "manual",
    ) -> JobQuestion:
        """يضيف سؤالاً واحداً كامل الخصائص (نوع، خيارات، كفاءة، صعوبة)."""
        text = (text or "").strip()
        if not text:
            raise ValidationError("نص السؤال مطلوب.")
        self._validate_extras(question_type, options, difficulty)
        question = JobQuestion(
            job_id=job_id, question=text, question_type=question_type,
            options=options or None, competency=(competency or "").strip() or None,
            difficulty=difficulty or None, category=category, rationale=rationale, source=source,
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

    def sync_bulk_text(self, job_id: int, raw_text: str) -> dict:
        """يزامن بنك أسئلة الوظيفة مع نص textarea واحد (سؤال لكل سطر). يرجع {updated, added, removed}."""
        lines = split_questions(raw_text)
        existing = self.list_for_job(job_id)
        common = min(len(existing), len(lines))

        updated = 0
        for i in range(common):
            if existing[i].question != lines[i]:
                existing[i].question = lines[i]
                updated += 1

        added: list[JobQuestion] = []
        for text in lines[common:]:
            question = JobQuestion(job_id=job_id, question=text, source="manual")
            self._questions.add(question)
            added.append(question)

        removed_count = 0
        if len(existing) > common:
            removed = existing[common:]
            removed_ids = [q.id for q in removed]
            self._session.execute(delete(InterviewAnswer).where(InterviewAnswer.question_id.in_(removed_ids)))
            for q in removed:
                self._questions.delete(q)
            removed_count = len(removed)

        return {"updated": updated, "added": len(added), "removed": removed_count}

    def add_ai_questions(self, job_id: int, result) -> list[JobQuestion]:
        """يضيف أسئلة مولّدة بالذكاء الاصطناعي (InterviewQuestions) إلى بنك الوظيفة."""
        sections = [
            ("cv_specific", result.cv_specific), ("technical", result.technical),
            ("behavioral", result.behavioral), ("leadership", result.leadership),
        ]
        created = []
        for category, items in sections:
            for item in items:
                question = JobQuestion(
                    job_id=job_id, question=item.question, category=category,
                    rationale=item.rationale, source="ai", question_type="text",
                )
                self._questions.add(question)
                created.append(question)
        return created

    def copy_from_job(self, target_job_id: int, source_job_id: int) -> int:
        """ينسخ أسئلة وظيفة أخرى إلى هذه الوظيفة (كقالب) متخطياً الأسئلة المكررة بالنص. يرجع عدد المنسوخ."""
        if target_job_id == source_job_id:
            raise ValidationError("اختر وظيفة مختلفة للنسخ منها.")
        existing = {q.question.strip().lower() for q in self.list_for_job(target_job_id)}
        copied = 0
        for q in self.list_for_job(source_job_id):
            if q.question.strip().lower() in existing:
                continue
            self._questions.add(JobQuestion(
                job_id=target_job_id, question=q.question, category=q.category, rationale=q.rationale,
                source=q.source, question_type=q.question_type, options=q.options,
                competency=q.competency, difficulty=q.difficulty,
            ))
            copied += 1
        return copied

    def update_question(self, question_id: int, text: str, **extras) -> JobQuestion:
        """تعديل نص السؤال، وأي من: competency, difficulty, question_type, options."""
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
        """حذف سؤال محدد مع كل إجابات المرشحين المرتبطة به (بغضّ النظر عن موضعه في البنك)."""
        question = self._get_or_raise(question_id)
        self._session.execute(delete(InterviewAnswer).where(InterviewAnswer.question_id == question_id))
        self._questions.delete(question)

    def _get_or_raise(self, question_id: int) -> JobQuestion:
        question = self._questions.get_by_id(question_id)
        if question is None:
            raise ValidationError("السؤال غير موجود.")
        return question

    # ------------------------------------------------------------ أوزان الكفاءات

    def competency_weights_text(self, job_id: int) -> str:
        job = self._session.get(Job, job_id)
        weights = (job.competency_weights if job else None) or {}
        return "\n".join(f"{name}: {value:g}" for name, value in weights.items())

    def set_competency_weights(self, job_id: int, raw_text: str) -> dict[str, float]:
        """يحفظ أوزان الكفاءات من نص «الاسم: الوزن» (سطر لكل كفاءة). نص فارغ = بدون أوزان."""
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