import threading
from concurrent.futures import ThreadPoolExecutor

from config.settings import get_settings
from core.constants import (
    AI_BACKGROUND_WORKERS, ANALYSIS_FAILED, ANALYSIS_PENDING, PHOTO_BACKGROUND_WORKERS,
)
from core.exceptions import SmartATSError
from core.logging import get_logger
from database.database import get_db_session

logger = get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=AI_BACKGROUND_WORKERS, thread_name_prefix="ai-analysis")
_photo_executor = ThreadPoolExecutor(max_workers=PHOTO_BACKGROUND_WORKERS, thread_name_prefix="face-crop")
_translation_executor = ThreadPoolExecutor(max_workers=AI_BACKGROUND_WORKERS, thread_name_prefix="translation")
_pending: set[int] = set()
_translating: set[int] = set()
_lock = threading.Lock()


def _ai_available() -> bool:
    settings = get_settings()
    return bool(settings.gemini_api_key or settings.alt_gemini_api_key)


def _set_status(candidate_id: int, status: str, error: str | None = None) -> None:
    from services.candidate_service import CandidateService

    with get_db_session() as session:
        candidate = CandidateService(session).get_by_id(candidate_id)
        if candidate is not None:
            candidate.analysis_status = status
            candidate.analysis_error = error


def submit(candidate_id: int) -> None:
    if not _ai_available():
        return
    with _lock:
        if candidate_id in _pending:
            return
        _pending.add(candidate_id)
    try:
        _set_status(candidate_id, ANALYSIS_PENDING)
        _executor.submit(_run, candidate_id)
    except Exception:
        with _lock:
            _pending.discard(candidate_id)
        raise


def submit_photo(candidate_id: int, page_png: bytes | None) -> None:
    if page_png:
        _photo_executor.submit(_run_photo, candidate_id, page_png)


def submit_translation(candidate_id: int) -> None:
    if not _ai_available():
        return
    with _lock:
        if candidate_id in _translating:
            return
        _translating.add(candidate_id)
    try:
        _translation_executor.submit(_run_translation, candidate_id)
    except Exception:
        with _lock:
            _translating.discard(candidate_id)
        raise


def is_pending(candidate_id: int) -> bool:
    with _lock:
        return candidate_id in _pending


def is_translating(candidate_id: int) -> bool:
    with _lock:
        return candidate_id in _translating


def _run(candidate_id: int) -> None:
    from services.candidate_service import CandidateService

    try:
        with get_db_session() as session:
            CandidateService(session).generate_ai_analysis(candidate_id, retry=True)
        logger.info("Background AI analysis finished for candidate %s", candidate_id)
        try:
            with get_db_session() as session:
                CandidateService(session).translate_analysis(candidate_id)
        except SmartATSError as exc:
            logger.warning("Analysis translation failed for candidate %s: %s", candidate_id, exc)
    except SmartATSError as exc:
        logger.warning("Background AI analysis failed for candidate %s: %s", candidate_id, exc)
        _safe_mark_failed(candidate_id, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in background analysis for candidate %s", candidate_id)
        _safe_mark_failed(candidate_id, f"خطأ غير متوقع: {exc}")
    finally:
        with _lock:
            _pending.discard(candidate_id)


def _run_translation(candidate_id: int) -> None:
    from ai.retry import call_with_retry
    from services.candidate_service import CandidateService

    def translate_data() -> None:
        with get_db_session() as session:
            CandidateService(session).translate_candidate(candidate_id)

    def translate_analysis() -> None:
        with get_db_session() as session:
            CandidateService(session).translate_analysis(candidate_id)

    try:
        for step in (translate_data, translate_analysis):
            try:
                call_with_retry(step)
            except SmartATSError as exc:
                logger.warning("Background translation step failed for candidate %s: %s", candidate_id, exc)
        logger.info("Background translation finished for candidate %s", candidate_id)
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error in background translation for candidate %s", candidate_id)
    finally:
        with _lock:
            _translating.discard(candidate_id)


def _safe_mark_failed(candidate_id: int, message: str) -> None:
    try:
        _set_status(candidate_id, ANALYSIS_FAILED, message[:500])
    except Exception:  # noqa: BLE001
        logger.exception("Could not record failed status for candidate %s", candidate_id)


def _run_photo(candidate_id: int, page_png: bytes) -> None:
    from document_processing.base import crop_face_from_image
    from services.candidate_service import CandidateService

    try:
        cropped = crop_face_from_image(page_png)
        if cropped is None:
            return
        with get_db_session() as session:
            service = CandidateService(session)
            candidate = service.get_by_id(candidate_id)
            if candidate is not None and not candidate.photo_path:
                service.set_photo(candidate_id, cropped[0])
    except Exception:  # noqa: BLE001
        logger.exception("Background face crop failed for candidate %s", candidate_id)