"""إعادة المحاولة مع انتظار متزايد عند أخطاء الحصة/الازدحام (429/503)."""

import random
import time
from collections.abc import Callable
from typing import TypeVar

from core.constants import AI_RETRY_BASE_SECONDS, AI_RETRY_MAX_ATTEMPTS
from core.exceptions import AIServiceError
from core.logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T")

# ملاحظة: لا نستخدم "rate" وحدها لأنها موجودة داخل كلمة generate
_RETRYABLE = ("429", "quota", "resource_exhausted", "rate limit", "503", "unavailable", "overloaded")


def is_retryable(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(token in message for token in _RETRYABLE)


def call_with_retry(fn: Callable[[], T], attempts: int = AI_RETRY_MAX_ATTEMPTS,
                    base: float = AI_RETRY_BASE_SECONDS) -> T:
    """ينفّذ fn ويعيد المحاولة عند خطأ قابل لها. كل محاولة تنشئ عميلاً جديداً فيتبدّل مفتاح API تلقائياً."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except AIServiceError as exc:
            if attempt == attempts or not is_retryable(exc):
                raise
            delay = base * 2 ** (attempt - 1) + random.uniform(0, 1)
            logger.warning("AI call failed (attempt %s/%s), retrying in %.1fs: %s", attempt, attempts, delay, exc)
            time.sleep(delay)
    raise AssertionError("unreachable")