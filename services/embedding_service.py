"""حساب وتخزين التمثيل الدلالي (Embedding) لمرشح أو وظيفة، مع كاش يمنع إعادة الحساب
إن لم يتغيّر النص، وحساب جماعي بالتوازي لتسريع المطابقة على عدة مرشحين/وظائف دفعة واحدة.
ملاحظة: نداء Gemini (I/O) يُنفَّذ داخل Threads، أما تعديل كائنات SQLAlchemy (غير آمن عبر
Threads متزامنة) فيتم دائماً في الخيط الرئيسي فقط."""

import concurrent.futures
import hashlib

from config.settings import get_settings
from core.constants import EMBEDDING_MODEL_NAME, MAX_WORKERS
from core.exceptions import AIServiceError
from core.logging import get_logger
from models.candidate import Candidate
from models.job import Job

logger = get_logger(__name__)


def _candidate_text(candidate: Candidate) -> str:
    from ai.analyzer import candidate_context

    return candidate_context(candidate)


def _job_text(job: Job) -> str:
    parts = [job.title]
    if job.department:
        parts.append(job.department)
    if job.required_experience_years:
        parts.append(f"الخبرة المطلوبة: {job.required_experience_years} سنة")
    if job.all_required_skills:
        parts.append("المهارات المطلوبة: " + ", ".join(job.all_required_skills))
    if job.preferred_industries:
        parts.append("المجالات المفضلة: " + ", ".join(job.preferred_industries))
    if job.description:
        parts.append(job.description)
    return "\n".join(parts)


class EmbeddingService:
    """يحسب Embedding عند الحاجة فقط ويخزّنه على الكائن نفسه (candidate.embedding / job.embedding)."""

    @staticmethod
    def _ai_available() -> bool:
        settings = get_settings()
        return bool(settings.gemini_api_key or settings.alt_gemini_api_key)

    # ------------------------------------------------------------ مفرد

    def ensure_candidate_embedding(self, candidate: Candidate) -> list[float] | None:
        return self._ensure(candidate, _candidate_text(candidate))

    def ensure_job_embedding(self, job: Job) -> list[float] | None:
        return self._ensure(job, _job_text(job))

    def _ensure(self, entity, text: str) -> list[float] | None:
        if not self._ai_available():
            return None

        input_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        meta = entity.embedding_meta or {}
        if (
            entity.embedding
            and meta.get("input_hash") == input_hash
            and meta.get("model") == EMBEDDING_MODEL_NAME
        ):
            return entity.embedding

        from ai.embeddings import embed_text

        try:
            vector = embed_text(text)
        except AIServiceError as exc:
            logger.warning("Embedding computation failed for %r: %s", entity, exc)
            return None

        entity.embedding = vector
        entity.embedding_meta = {"input_hash": input_hash, "model": EMBEDDING_MODEL_NAME}
        return vector

    # ------------------------------------------------------------ جماعي بالتوازي

    def ensure_many_candidate_embeddings(self, candidates: list[Candidate]) -> None:
        self._ensure_many(candidates, _candidate_text)

    def ensure_many_job_embeddings(self, jobs: list[Job]) -> None:
        self._ensure_many(jobs, _job_text)

    def _ensure_many(self, entities: list, text_fn) -> None:
        """يحسب النصوص والهاشات في الخيط الرئيسي، ثم يستدعي Gemini بالتوازي (Threads)،
        ثم يخزّن النتائج في الخيط الرئيسي فقط بعد اكتمال كل نداء - آمن مع SQLAlchemy Session."""
        if not self._ai_available() or not entities:
            return

        pending: list[tuple] = []
        for entity in entities:
            text = text_fn(entity)
            input_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            meta = entity.embedding_meta or {}
            if (
                entity.embedding
                and meta.get("input_hash") == input_hash
                and meta.get("model") == EMBEDDING_MODEL_NAME
            ):
                continue
            pending.append((entity, text, input_hash))

        if not pending:
            return

        from ai.embeddings import embed_text

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(pending))) as executor:
            futures = {
                executor.submit(embed_text, text): (entity, input_hash)
                for entity, text, input_hash in pending
            }
            for future in concurrent.futures.as_completed(futures):
                entity, input_hash = futures[future]
                try:
                    vector = future.result()
                except AIServiceError as exc:
                    logger.warning("Embedding computation failed for %r: %s", entity, exc)
                    continue
                entity.embedding = vector
                entity.embedding_meta = {"input_hash": input_hash, "model": EMBEDDING_MODEL_NAME}