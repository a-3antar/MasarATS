"""قراءة نص صفحة صورية (سيرة ذاتية ممسوحة أو مصممة كصورة) عبر Gemini Vision (google-genai)."""

import json

from ai.key_rotator import get_next_key
from config.settings import get_settings
from core.exceptions import AIServiceError
from core.logging import get_logger

logger = get_logger(__name__)

_TRANSCRIBE_PROMPT = (
    "انسخ كل النص الظاهر في هذه الصورة كما هو حرفياً وبنفس لغته (عربي أو إنجليزي)، "
    "سطراً بسطر، بدون ترجمة أو تلخيص أو شرح أو إضافة. "
    "إذا كان التصميم بعمودين فاقرأ كل عمود كاملاً على حدة. "
    "أعد النص فقط."
)


def _client():
    """عميل genai مستقل لكل نداء - يستخدم المفتاح التالي في التبديل الدوري. آمن للتوازي."""
    from google import genai

    return genai.Client(api_key=get_next_key())


def transcribe_image(image_bytes: bytes, mime_type: str = "image/png") -> str:
    """يرسل صورة لـ Gemini ويرجع النص المكتوب فيها. يرفع AIServiceError برسالة مفهومة عند الفشل."""
    settings = get_settings()
    if not settings.gemini_api_key and not settings.alt_gemini_api_key:
        raise AIServiceError("قراءة الصفحات الصورية تحتاج GEMINI_API_KEY في ملف .env")

    try:
        from google.genai import types
    except ImportError as exc:
        raise AIServiceError("مكتبة google-genai غير مثبّتة.") from exc

    try:
        client = _client()
        response = client.models.generate_content(
            model=settings.ai_model,
            contents=[
                _TRANSCRIBE_PROMPT,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
            config={"temperature": 0.0, "max_output_tokens": 8192},
        )
        text = (response.text or "").strip()
    except Exception as exc:
        logger.error("Gemini vision transcription failed: %s", exc)
        raise AIServiceError(_friendly_error(exc)) from exc

    if not text:
        raise AIServiceError("لم يتمكن الذكاء الاصطناعي من قراءة أي نص في الصفحة (الصورة غير واضحة أو فارغة).")
    return text


def _friendly_error(exc: Exception) -> str:
    """يحوّل أخطاء Gemini التقنية إلى رسالة عربية مفهومة للمستخدم."""
    message = str(exc).lower()
    if "api key" in message or "api_key" in message or "permission" in message or "403" in message:
        return "مفتاح GEMINI_API_KEY غير صالح أو لا يملك صلاحية. تحقق منه في ملف .env."
    if "quota" in message or "429" in message or "rate" in message or "resource" in message:
        return "تم تجاوز حد استخدام Gemini (الحصة). انتظر قليلاً ثم حاول مرة أخرى."
    if "timeout" in message or "deadline" in message or "connect" in message or "network" in message:
        return "تعذّر الاتصال بخدمة Gemini. تحقق من الإنترنت وحاول مرة أخرى."
    if "safety" in message or "blocked" in message or "finish_reason" in message or "valid part" in message:
        return "رفض الذكاء الاصطناعي قراءة الصفحة (حُجب المحتوى). جرّب ملفاً آخر."
    return f"فشل قراءة الصفحة عبر Gemini: {exc}"


def detect_face_box(image_bytes: bytes, mime_type: str = "image/png") -> tuple[float, float, float, float] | None:
    """
    يطلب من Gemini صندوق وجه الشخص الأبرز في الصورة.
    يرجع (x_min, y_min, x_max, y_max) كنسب من 0 إلى 1، أو None إن لم يوجد وجه أو فشل الطلب.
    """
    settings = get_settings()
    if not settings.gemini_api_key and not settings.alt_gemini_api_key:
        return None

    try:
        from google.genai import types

        client = _client()
        prompt = (
            "حدد وجه الشخص الظاهر في صورته الشخصية داخل هذه الصفحة (إن وُجد). "
            'أعد JSON فقط بهذا الشكل: {"found": true, "box": [ymin, xmin, ymax, xmax]} '
            "حيث القيم أعداد صحيحة من 0 إلى 1000 نسبةً لأبعاد الصورة. "
            'وإن لم يوجد وجه أعد {"found": false}.'
        )
        response = client.models.generate_content(
            model=settings.ai_model,
            contents=[prompt, types.Part.from_bytes(data=image_bytes, mime_type=mime_type)],
            config={"temperature": 0.0, "response_mime_type": "application/json"},
        )
        data = json.loads(response.text)
        if not data.get("found"):
            return None

        ymin, xmin, ymax, xmax = (float(v) / 1000 for v in data["box"])
        if not (0 <= xmin < xmax <= 1 and 0 <= ymin < ymax <= 1):
            return None
        return xmin, ymin, xmax, ymax
    except Exception as exc:  # noqa: BLE001 - فشل الاكتشاف لا يوقف رفع السيرة
        logger.warning("Gemini face detection failed: %s", exc)
        return None