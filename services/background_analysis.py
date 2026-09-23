"""تشغيل تحليل الذكاء الاصطناعي للمرشحين في الخلفية حتى لا يتعطل رفع السير أو الواجهة."""

import threading
from concurrent.futures import ThreadPoolExecutor

from config.settings import get_settings
from core.constants import AI_BACKGROUND_WORKERS
from core.exceptions import SmartATSError
from core.logging import get_logger
from database.database import get_db_session

logger = get_logger(__name__)

# الحالة على مستوى الوحدة (module) تبقى حية بين إعادات تشغيل Streamlit (rerun)
_executor = ThreadPoolExecutor(max_workers=AI_BACKGROUND_WORKERS, thread_name_prefix="ai-analysis")
_pending: set[int] = set()
_lock = threading.Lock()


def _ai_available() -> bool:
    settings = get_settings()
    return bool(settings.gemini_api_key or settings.alt_gemini_api_key)


def submit(candidate_id: int) -> None:
    """يجدول تحليل مرشح في الخلفية. يجب استدعاؤها بعد commit حفظ المرشح. لا تفعل شيئاً بدون مفتاح API."""
    if not _ai_available():
        return
    with _lock:
        if candidate_id in _pending:
            return
        _pending.add(candidate_id)
    _executor.submit(_run, candidate_id)


def is_pending(candidate_id: int) -> bool:
    """هل تحليل هذا المرشح قيد التنفيذ أو في الانتظار؟"""
    with _lock:
        return candidate_id in _pending


def _run(candidate_id: int) -> None:
    """يعمل داخل Thread خلفي بجلسة قاعدة بيانات مستقلة. أي فشل يُسجَّل فقط ولا يؤثر على التطبيق."""
    try:
        from services.candidate_service import CandidateService  # استيراد متأخر لتفادي circular import

        with get_db_session() as session:
            CandidateService(session).generate_ai_analysis(candidate_id)
        logger.info("Background AI analysis finished for candidate %s", candidate_id)
    except SmartATSError as exc:
        logger.warning("Background AI analysis failed for candidate %s: %s", candidate_id, exc)
    except Exception:  # noqa: BLE001 - لا نريد أن يموت الـ worker بصمت
        logger.exception("Unexpected error in background analysis for candidate %s", candidate_id)
    finally:
        with _lock:
            _pending.discard(candidate_id)