"""حساب التمثيل الدلالي (Embedding) عبر Gemini - يُستخدم فقط من طبقة المطابقة الدلالية."""

import math

from ai.key_rotator import get_next_key
from config.settings import get_settings
from core.constants import EMBEDDING_MODEL_NAME
from core.exceptions import AIServiceError
from core.logging import get_logger

logger = get_logger(__name__)


def embed_text(text: str) -> list[float]:
    """يرجع متجه التمثيل الدلالي للنص. يرفع AIServiceError عند غياب المفتاح أو فشل النداء."""
    settings = get_settings()
    if not settings.gemini_api_key and not settings.alt_gemini_api_key:
        raise AIServiceError("المطابقة الدلالية تحتاج GEMINI_API_KEY في ملف .env")
    if not (text or "").strip():
        raise AIServiceError("لا يوجد نص لحساب التمثيل الدلالي منه.")

    try:
        from google import genai
    except ImportError as exc:
        raise AIServiceError("مكتبة google-genai غير مثبّتة.") from exc

    try:
        client = genai.Client(api_key=get_next_key())
        response = client.models.embed_content(model=EMBEDDING_MODEL_NAME, contents=text[:8000])
        return list(response.embeddings[0].values)
    except Exception as exc:
        logger.error("Gemini embedding call failed: %s", exc)
        raise AIServiceError(f"فشل حساب التمثيل الدلالي: {exc}") from exc


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """تشابه جيب التمام بين متجهين. يرجع 0.0 عند عدم التطابق في الطول أو متجه فارغ."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)