"""
تبديل دوري (round-robin) بين مفاتيح Gemini API المتاحة، بشكل آمن للـ Threads.

المشكلة التي يحلّها هذا الملف: عند معالجة عدة سير ذاتية بالتوازي (ThreadPoolExecutor
في candidate_service.py و upload_cv.py)، يجب توزيع نداءات Gemini على أكثر من مفتاح
واحد إن توفر، بدل ضرب مفتاح واحد بكل الحمل والوصول لحد الحصة (rate limit) بسرعة.
"""

import itertools
import threading

from config.settings import get_settings
from core.exceptions import AIServiceError

_lock = threading.Lock()
_key_cycle: itertools.cycle | None = None


def _build_key_cycle() -> itertools.cycle:
    settings = get_settings()
    keys = [k for k in (settings.gemini_api_key, settings.alt_gemini_api_key) if k]
    if not keys:
        raise AIServiceError("لم يتم ضبط أي مفتاح GEMINI_API_KEY في ملف .env")
    return itertools.cycle(keys)


def get_next_key() -> str:
    """يرجع المفتاح التالي بالتبادل. يرفع AIServiceError إن لم يوجد أي مفتاح مضبوط."""
    global _key_cycle
    with _lock:
        if _key_cycle is None:
            _key_cycle = _build_key_cycle()
        return next(_key_cycle)