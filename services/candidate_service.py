"""
خدمة المرشحين.
تُدير سير عمل رفع السيرة الذاتية بالكامل:
ملف → استخلاص نص وصورة → (AI أو استخلاص احتياطي بسيط) → تحقق Pydantic → حفظ في القاعدة.
كما تدير تعديل المرشح وترجمة بياناته للعربية (مع بقاء الأصل الإنجليزي).
"""

import hashlib
import io
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from ai.fallback_extractor import extract_basic_profile
from ai.schemas import CandidateProfile, ExperienceItem
from config.settings import BASE_DIR, get_settings
from core.constants import (
    ALLOWED_CV_EXTENSIONS,
    MAX_CV_FILE_SIZE_MB,
    PHOTO_MAX_SIDE_PX,
    PHOTOS_SUBDIR,
)
from core.exceptions import AIServiceError, DuplicateCandidateError, ValidationError
from core.logging import get_logger
from document_processing.factory import DocumentParserFactory
from models.candidate import Candidate
from repositories.candidate_repository import CandidateRepository
from services.experience_calculator import estimate_total_years
from services.duplicate_detector import DuplicateDetector

from concurrent.futures import ThreadPoolExecutor


logger = get_logger(__name__)

PHOTOS_DIR = BASE_DIR / PHOTOS_SUBDIR

# الحقول المسموح تعديلها من الواجهة (قائمة بيضاء لمنع تعديل حقول داخلية مثل file_hash)
_EDITABLE_FIELDS = {
    "full_name", "email", "phone", "location", "age", "current_position", "total_experience_years",
    "summary", "skills", "technical_skills", "computer_skills", "managerial_skills",
    "soft_skills", "industries", "previous_companies", "previous_positions",
    "linkedin_url", "marital_status", "military_status", "languages",
    "applied_job", "status", "rating", "expected_salary", "notice_period_days", "recruiter_notes",
}

# الحقول التي تُترجم (أسماء الشركات والتواريخ تبقى كما هي)
_TRANSLATABLE_FIELDS = (
    "current_position", "location", "summary",
    "technical_skills", "computer_skills", "managerial_skills", "soft_skills", "skills",
    "industries", "previous_positions", "languages", "marital_status", "military_status",
    "education", "experience",
)
# مفاتيح داخل عناصر education/experience لا نقبل ترجمتها
_NON_TRANSLATED_KEYS = {"company", "start_date", "end_date", "graduation_year"}
_TARGET_LANGUAGE_NAMES = {"ar": "Arabic"}


class CandidateService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._candidates = CandidateRepository(session)
        self._duplicates = DuplicateDetector(self._candidates)


    def process_cv_file(self, file_path: str, original_filename: str) -> Candidate:
        """
        السير الكامل لمعالجة ملف سيرة ذاتية واحد وحفظه كمرشح.
        يرفع ValidationError لملف غير مدعوم، أو DuplicateCandidateError لملف/مرشح مكرر.
        تطابق الاسم فقط لا يمنع الحفظ، بل يوضع في candidate.duplicate_warning للعرض.
        تحليل الذكاء الاصطناعي الشامل لا يتم هنا: تجدوله الواجهة في الخلفية بعد الـ commit
        (services/background_analysis.py).
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

        with ThreadPoolExecutor(max_workers=1) as photo_executor:
            photo_future = photo_executor.submit(parser.extract_photo, file_path)

            profile = self._extract_profile(raw_text, fallback_name=Path(original_filename).stem)
            full_name = profile.full_name or Path(original_filename).stem

            matches = self._duplicates.find_duplicates(
                full_name=full_name,
                email=profile.email,
                phone=profile.phone,
                linkedin_url=profile.linkedin_url,
            )
            strong = next((m for m in matches if m.is_strong), None)
            if strong is not None:
                raise DuplicateCandidateError(f"مرشح مكرر: {strong.describe()}")

            photo = photo_future.result()

        candidate = Candidate(
            full_name=full_name,
            email=profile.email,
            phone=profile.phone,
            linkedin_url=profile.linkedin_url,
            location=profile.location,
            age=profile.age,
            photo_path=self._save_photo(photo[0], file_hash[:16]) if photo else None,
            marital_status=profile.marital_status,
            military_status=profile.military_status,
            languages=profile.languages,
            current_position=profile.current_position,
            total_experience_years=estimate_total_years(profile.experience) or profile.total_experience_years,
            skills=profile.skills,
            technical_skills=profile.technical_skills,
            computer_skills=profile.computer_skills,
            managerial_skills=profile.managerial_skills,
            soft_skills=profile.soft_skills,
            industries=profile.industries,
            previous_companies=self._unique_field(profile.experience, "company"),
            previous_positions=self._unique_field(profile.experience, "position"),
            education=[e.model_dump() for e in profile.education],
            experience=[e.model_dump() for e in profile.experience],
            summary=profile.summary,
            status="New",
            source_filename=original_filename,
            file_hash=file_hash,
            raw_text=raw_text,
            ai_analyzed=self._ai_available(),
        )
        self._candidates.add(candidate)
        self._assign_code(candidate)

        # سمة مؤقتة (غير محفوظة في القاعدة) تقرؤها صفحة الرفع لعرض التنبيه
        candidate.duplicate_warning = " | ".join(m.describe() for m in matches) or None

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
    def _unique_field(experience: list[ExperienceItem], attr: str) -> list[str]:
        """قيم حقل نصي (company / position) من قائمة الخبرات بنفس الترتيب وبدون تكرار."""
        values: list[str] = []
        seen: set[str] = set()
        for item in experience:
            value = (getattr(item, attr, None) or "").strip()
            if value and value.lower() not in seen:
                seen.add(value.lower())
                values.append(value)
        return values

    @staticmethod
    def _assign_code(candidate: Candidate) -> None:
        """كود مقروء فريد مثل CAND-2026-001 (يعتمد على id بعد الـ flush)."""
        candidate.candidate_code = f"CAND-{date.today().year}-{candidate.id:03d}"

    @staticmethod
    def _ai_available() -> bool:
        return bool(get_settings().gemini_api_key)

    @staticmethod
    def _compute_file_hash(file_path: str) -> str:
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    # ------------------------------------------------------------------ الصور

    @staticmethod
    def _save_photo(image_bytes: bytes, name_stem: str) -> str | None:
        """
        يحفظ الصورة بصيغة JPEG موحّدة ومصغّرة، ويرجع المسار النسبي لجذر المشروع.
        يرجع None عند الفشل (صيغة غير مقروءة مثلاً) ولا يرفع استثناء.
        """
        try:
            from PIL import Image

            with Image.open(io.BytesIO(image_bytes)) as source:
                if source.mode in ("RGBA", "LA", "P"):
                    rgba = source.convert("RGBA")
                    image = Image.new("RGB", rgba.size, "white")  # خلفية بيضاء بدل الأسود للشفافية
                    image.paste(rgba, mask=rgba.split()[-1])
                else:
                    image = source.convert("RGB")

            image.thumbnail((PHOTO_MAX_SIDE_PX, PHOTO_MAX_SIDE_PX))
            PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
            target = PHOTOS_DIR / f"{name_stem}.jpg"
            image.save(target, format="JPEG", quality=90)
            return target.relative_to(BASE_DIR).as_posix()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save candidate photo: %s", exc)
            return None

    @staticmethod
    def _delete_photo_file(relative_path: str | None) -> None:
        if relative_path:
            (BASE_DIR / relative_path).unlink(missing_ok=True)

    @staticmethod
    def photo_absolute_path(candidate: Candidate) -> Path | None:
        """المسار الكامل لصورة المرشح إن كانت موجودة فعلاً على القرص."""
        if not candidate.photo_path:
            return None
        path = BASE_DIR / candidate.photo_path
        return path if path.exists() else None

    def set_photo(self, candidate_id: int, image_bytes: bytes) -> None:
        """استبدال صورة المرشح بصورة مرفوعة يدوياً."""
        candidate = self._get_or_raise(candidate_id)
        new_path = self._save_photo(image_bytes, f"candidate_{candidate_id}_{uuid.uuid4().hex[:8]}")
        if new_path is None:
            raise ValidationError("تعذّر قراءة الصورة. استخدم ملف PNG أو JPG صالحاً.")
        self._delete_photo_file(candidate.photo_path)
        candidate.photo_path = new_path

    def remove_photo(self, candidate_id: int) -> None:
        candidate = self._get_or_raise(candidate_id)
        self._delete_photo_file(candidate.photo_path)
        candidate.photo_path = None

    # ---------------------------------------------------------- الترجمة

    def translate_candidate(self, candidate_id: int, target: str = "ar") -> None:
        """
        يترجم بيانات المرشح إلى اللغة المطلوبة ويخزّنها في عمود translations
        بجانب الأصل (الأصل لا يُلمس أبداً). يرفع AIServiceError عند الفشل.
        """
        if target not in _TARGET_LANGUAGE_NAMES:
            raise ValidationError(f"لغة الترجمة غير مدعومة: {target}")

        candidate = self._get_or_raise(candidate_id)

        payload: dict = {}
        for name in _TRANSLATABLE_FIELDS:
            value = getattr(candidate, name)
            if name == "previous_positions" and not value:
                value = self._positions_from_experience(candidate.experience)
            if value:
                payload[name] = value
        if not payload:
            raise ValidationError("لا توجد بيانات لترجمتها.")

        from ai.gemini_service import GeminiService

        translated = GeminiService().translate_json(payload, _TARGET_LANGUAGE_NAMES[target])
        cleaned = self._clean_translation(payload, translated)
        if not cleaned:
            raise AIServiceError("لم تُرجع الترجمة بياناتٍ صالحة.")

        translations = dict(candidate.translations or {})
        translations[target] = cleaned
        candidate.translations = translations  # إعادة إسناد ضرورية لاكتشاف تغيّر عمود JSON

    @staticmethod
    def _positions_from_experience(experience: list[dict] | None) -> list[str]:
        positions: list[str] = []
        seen: set[str] = set()
        for item in experience or []:
            value = (item.get("position") or "").strip()
            if value and value.lower() not in seen:
                seen.add(value.lower())
                positions.append(value)
        return positions

    @staticmethod
    def _clean_translation(original: dict, translated: dict) -> dict:
        """يقبل من ناتج الترجمة فقط ما يطابق بنية الأصل (نفس النوع وعدد العناصر)، ويعيد الحقول غير المترجمة."""
        cleaned: dict = {}
        for key, orig in original.items():
            new = translated.get(key)
            if new in (None, "", []):
                continue
            if isinstance(orig, list):
                if not isinstance(new, list) or len(new) != len(orig):
                    continue
                if orig and isinstance(orig[0], dict):
                    if not all(isinstance(n, dict) for n in new):
                        continue
                    merged_items = []
                    for o, n in zip(orig, new):
                        merged = dict(o)
                        for k, v in n.items():
                            if k in o and k not in _NON_TRANSLATED_KEYS:
                                merged[k] = v
                        merged_items.append(merged)
                    cleaned[key] = merged_items
                    continue
            elif not isinstance(new, str):
                continue
            cleaned[key] = new
        return cleaned

    # ---------------------------------------------------------- CRUD والبحث

    def _get_or_raise(self, candidate_id: int) -> Candidate:
        candidate = self._candidates.get_by_id(candidate_id)
        if candidate is None:
            raise ValidationError("المرشح غير موجود.")
        return candidate

    def get_by_id(self, candidate_id: int) -> Candidate | None:
        return self._candidates.get_by_id(candidate_id)

    def update_candidate(self, candidate_id: int, **fields) -> Candidate:
        """تعديل بيانات مرشح موجود (الحقول المسموحة فقط). تُمسح الترجمة القديمة إن تغيّر محتوى مترجَم."""
        candidate = self._get_or_raise(candidate_id)

        unknown = set(fields) - _EDITABLE_FIELDS
        if unknown:
            raise ValidationError(f"حقول غير قابلة للتعديل: {', '.join(sorted(unknown))}")
        if "full_name" in fields and not (fields["full_name"] or "").strip():
            raise ValidationError("الاسم الكامل مطلوب.")

        content_changed = any(
            name in _TRANSLATABLE_FIELDS and (getattr(candidate, name) or None) != (value or None)
            for name, value in fields.items()
        )

        for name, value in fields.items():
            setattr(candidate, name, value)
        if content_changed and candidate.translations:
            candidate.translations = {}  # الترجمة القديمة لم تعد مطابقة للأصل
        return candidate

    def create_manual(self, **fields) -> Candidate:
        """إنشاء مرشح يدوياً (بدون رفع ملف) - تُستخدم من نموذج إدخال يدوي في الواجهة."""
        if not fields.get("full_name"):
            raise ValidationError("الاسم الكامل مطلوب.")
        fields.setdefault("status", "New")
        candidate = Candidate(**fields)
        self._candidates.add(candidate)
        self._assign_code(candidate)
        return candidate

    def list_all(self, limit: int = 200) -> list[Candidate]:
        return self._candidates.list_all(limit=limit)

    def search(self, query: str) -> list[Candidate]:
        return self._candidates.search(query) if query else self._candidates.list_all()

    def generate_ai_analysis(self, candidate_id: int) -> dict:
        """يولّد تحليل الذكاء الاصطناعي الشامل للمرشح ويخزّنه (كاش) في عمود ai_analysis. يرفع AIServiceError عند الفشل."""
        from ai.analyzer import analyze_candidate

        candidate = self._get_or_raise(candidate_id)
        analysis = analyze_candidate(candidate)
        candidate.ai_analysis = analysis.model_dump()
        return candidate.ai_analysis