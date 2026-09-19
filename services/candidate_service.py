"""
خدمة المرشحين.
تُدير سير عمل رفع السيرة الذاتية بالكامل:
ملف → استخلاص نص → (AI أو استخلاص احتياطي بسيط) → تحقق Pydantic → حفظ في القاعدة.
"""

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from ai.fallback_extractor import extract_basic_profile
from ai.schemas import CandidateProfile
from config.settings import get_settings
from core.constants import ALLOWED_CV_EXTENSIONS, MAX_CV_FILE_SIZE_MB
from core.exceptions import AIServiceError, DuplicateCandidateError, ValidationError
from core.logging import get_logger
from document_processing.factory import DocumentParserFactory
from models.candidate import Candidate
from repositories.candidate_repository import CandidateRepository

logger = get_logger(__name__)


class CandidateService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._candidates = CandidateRepository(session)

    def process_cv_file(self, file_path: str, original_filename: str) -> Candidate:
        """
        السير الكامل لمعالجة ملف سيرة ذاتية واحد وحفظه كمرشح.
        يرفع ValidationError لملف غير مدعوم، أو DuplicateCandidateError لملف مكرر.
        """
        extension = Path(original_filename).suffix.lower()
        if extension not in ALLOWED_CV_EXTENSIONS:
            raise ValidationError(f"صيغة الملف غير مدعومة حالياً: {extension}")

        file_size_mb = Path(file_path).stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_CV_FILE_SIZE_MB:
            raise ValidationError(f"حجم الملف يتجاوز الحد المسموح ({MAX_CV_FILE_SIZE_MB} ميجابايت).")

        file_hash = self._compute_file_hash(file_path)
        existing = self._candidates.get_by_file_hash(file_hash)
        if existing is not None:
            raise DuplicateCandidateError(f"هذا الملف مرفوع مسبقاً للمرشح: {existing.full_name}")

        parser = DocumentParserFactory.get_parser(file_path)
        raw_text = parser.extract_text(file_path)

        profile = self._extract_profile(raw_text, fallback_name=Path(original_filename).stem)

        candidate = Candidate(
            full_name=profile.full_name or Path(original_filename).stem,
            email=profile.email,
            phone=profile.phone,
            location=profile.location,
            current_position=profile.current_position,
            total_experience_years=profile.total_experience_years,
            skills=profile.skills,
            education=[e.model_dump() for e in profile.education],
            experience=[e.model_dump() for e in profile.experience],
            summary=profile.summary,
            source_filename=original_filename,
            file_hash=file_hash,
            raw_text=raw_text,
            ai_analyzed=self._ai_available(),
        )
        self._candidates.add(candidate)
        logger.info("Candidate created from CV upload: %s (%s)", candidate.full_name, original_filename)
        return candidate

    def _extract_profile(self, raw_text: str, fallback_name: str) -> CandidateProfile:
        """يحاول الاستخلاص عبر Gemini إن توفر مفتاح API، وإلا يستخدم المستخلص الاحتياطي البسيط."""
        if not self._ai_available():
            logger.info("GEMINI_API_KEY not set - using basic fallback extraction.")
            return extract_basic_profile(raw_text, fallback_name)

        try:
            from ai.gemini_service import GeminiService

            provider = GeminiService()
            result = provider.extract_structured(raw_text, CandidateProfile)
            return result  # type: ignore[return-value]
        except AIServiceError as exc:
            logger.warning("AI extraction failed, falling back to basic extraction: %s", exc)
            return extract_basic_profile(raw_text, fallback_name)

    @staticmethod
    def _ai_available() -> bool:
        return bool(get_settings().gemini_api_key)

    @staticmethod
    def _compute_file_hash(file_path: str) -> str:
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def create_manual(self, **fields) -> Candidate:
        """إنشاء مرشح يدوياً (بدون رفع ملف) - تُستخدم من نموذج إدخال يدوي في الواجهة."""
        if not fields.get("full_name"):
            raise ValidationError("الاسم الكامل مطلوب.")
        candidate = Candidate(**fields)
        self._candidates.add(candidate)
        return candidate

    def list_all(self, limit: int = 200) -> list[Candidate]:
        return self._candidates.list_all(limit=limit)

    def search(self, query: str) -> list[Candidate]:
        return self._candidates.search(query) if query else self._candidates.list_all()
