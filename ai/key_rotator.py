
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
    global _key_cycle
    with _lock:
        if _key_cycle is None:
            _key_cycle = _build_key_cycle()
        return next(_key_cycle)
