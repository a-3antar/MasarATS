"""خدمة بنك أسئلة الوظيفة: إضافة/تعديل/حذف أسئلة، وتوليدها بالذكاء الاصطناعي، مرتبطة بالوظيفة
فقط (وليس بمرشح معين) حتى يمكن إعادة استخدامها مع أي مرشح متقدم لنفس الوظيفة.

التعديل الجماعي (sync_bulk_text) يقارن السطور الجديدة بالأسئلة الحالية حسب الترتيب:
- سطر في نفس الموضع بنص مختلف → تحديث نص نفس السؤال (يحافظ على الإجابات المرتبطة به).
- سطور زائدة في النهاية → أسئلة جديدة.
- سطور أقل من الموجود → حذف الأسئلة الزائدة من النهاية (مع إجاباتها).
لحذف سؤال محدد في منتصف القائمة بدقة دون التأثير على البقية، تُستخدم delete_question مباشرة."""

import re

from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.exceptions import ValidationError
from models.interview_answer import InterviewAnswer
from models.job_question import JobQuestion
from repositories.job_question_repository import JobQuestionRepository

_CATEGORY_LABELS = {
    "cv_specific": "خاص بالسيرة الذاتية",
    "technical": "تقني",
    "behavioral": "سلوكي",
    "leadership": "قيادي",
}


def split_questions(raw: str) -> list[str]:
    """يقسّم نصاً حراً إلى أسئلة منفصلة: كل سطر جديد أو علامة استفهام (عربية أو إنجليزية) يفصل بين سؤالين."""
    parts = re.split(r"[\n؟?]+", raw or "")
    return [p.strip() for p in parts if p.strip()]


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
        return self.questions_as_text(job_id)

    def add_questions_from_text(self, job_id: int, raw_text: str) -> list[JobQuestion]:
        """يضيف عدة أسئلة دفعة واحدة من نص حر (مفصولة بسطر جديد أو علامة استفهام)."""
        texts = split_questions(raw_text)
        if not texts:
            raise ValidationError("لم يتم إدخال أي سؤال صالح.")
        created = []
        for text in texts:
            question = JobQuestion(job_id=job_id, question=text, source="manual")
            self._questions.add(question)
            created.append(question)
        return created

    def sync_bulk_text(self, job_id: int, raw_text: str) -> dict:
        """يزامن بنك أسئلة الوظيفة بالكامل مع نص textarea واحد (سؤال لكل سطر)، محافظاً على
        الأسئلة غير المتغيّرة موضعياً (وبالتالي إجاباتها). يرجع ملخصاً: {updated, added, removed}."""
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
                    rationale=item.rationale, source="ai",
                )
                self._questions.add(question)
                created.append(question)
        return created

    def update_question(self, question_id: int, text: str) -> JobQuestion:
        question = self._get_or_raise(question_id)
        text = (text or "").strip()
        if not text:
            raise ValidationError("نص السؤال مطلوب.")
        question.question = text
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

    @staticmethod
    def category_label(category: str | None) -> str:
        return _CATEGORY_LABELS.get(category or "", "") if category else "يدوي"
