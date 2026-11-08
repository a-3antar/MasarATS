"""ترحيل لمرة واحدة: ترجمة المرشحين القدامى وحفظ النسختين العربية والإنجليزية.

التشغيل من جذر المشروع:
    python migrate_translations.py
    python migrate_translations.py --workers 3     (عدد خيوط الترجمة، الافتراضي 2)
    python migrate_translations.py --force         (إعادة التنفيذ حتى لو نُفّذ من قبل)

بعد نجاح كل المرشحين يُنشأ ملف علامة فلا يعمل السكربت مرة ثانية إلا بـ --force.
"""
import argparse
import concurrent.futures
import sys
import time
from services.candidate_service import (
    ANALYSIS_KEYS, CandidateService, analysis_language, candidate_language,
)
from sqlalchemy import select

from ai.retry import call_with_retry
from config.settings import BASE_DIR, get_settings
from core.exceptions import SmartATSError, ValidationError
from core.logging import get_logger, setup_logging
from database.database import get_db_session, init_db
from models.candidate import Candidate
from services.candidate_service import CandidateService, candidate_language

logger = get_logger("migrate_translations")

MARKER = BASE_DIR / "data" / ".translations_migrated"
PAUSE_SECONDS = 0.5


def _target_of(source: str) -> str:
    return "en" if source == "ar" else "ar"

def _pending_ids() -> dict[int, bool]:
    """id ← هل يحتاج ترجمة البيانات (وإلا فترجمة التحليل فقط)."""
    pending: dict[int, bool] = {}
    with get_db_session() as session:
        for candidate in session.scalars(select(Candidate).order_by(Candidate.id)):
            source = candidate_language(candidate)
            if candidate.original_language != source:
                candidate.original_language = source
            translations = candidate.translations or {}

            saved = translations.get(_target_of(source))
            needs_main = not saved or (bool(candidate.full_name) and "full_name" not in saved)

            analysis = candidate.ai_analysis or {}
            needs_analysis = False
            if any(analysis.get(k) for k in ANALYSIS_KEYS):
                bucket = translations.get(_target_of(analysis_language(analysis))) or {}
                needs_analysis = not bucket.get("ai_analysis")

            if needs_main or needs_analysis:
                pending[candidate.id] = needs_main
    return pending


def _translate_one(candidate_id: int, needs_main: bool) -> tuple[int, str, str]:
    def work() -> None:
        with get_db_session() as session:
            service = CandidateService(session)
            if needs_main:
                service.translate_candidate(candidate_id, force=True)
            service.translate_analysis(candidate_id)

    try:
        call_with_retry(work)
        status, message = "ok", ""
    except ValidationError as exc:
        status, message = "skipped", str(exc)
    except SmartATSError as exc:
        status, message = "failed", str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error for candidate %s", candidate_id)
        status, message = "failed", str(exc)
    time.sleep(PAUSE_SECONDS)
    return candidate_id, status, message

def main() -> int:
    parser = argparse.ArgumentParser(description="ترجمة المرشحين القدامى (مرة واحدة).")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    setup_logging()
    if MARKER.exists() and not args.force:
        print("تم تنفيذ الترحيل من قبل. استخدم --force لإعادته.")
        return 0
    if not get_settings().ai_enabled:
        print("لا يوجد GEMINI_API_KEY في ملف .env — لا يمكن الترجمة.")
        return 1

    init_db()
    ids = _pending_ids()
    if not ids:
        print("لا يوجد مرشحون يحتاجون ترجمة.")
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.touch()
        return 0

    print(f"عدد المرشحين المطلوب ترجمتهم: {len(ids)}")
    ok = skipped = 0
    failed: list[tuple[int, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(_translate_one, cid, needs_main) for cid, needs_main in ids.items()]
        for done, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            cid, status, message = future.result()
            if status == "ok":
                ok += 1
            elif status == "skipped":
                skipped += 1
            else:
                failed.append((cid, message))
            print(f"[{done}/{len(ids)}] مرشح #{cid}: {status}" + (f" — {message}" if message else ""))

    print(f"\nتمت الترجمة: {ok} | تخطي: {skipped} | فشل: {len(failed)}")
    if failed:
        print("فشل المرشحون التاليون (أعد تشغيل السكربت لمحاولتهم مجدداً):")
        for cid, message in failed:
            print(f"  #{cid}: {message}")
        return 1

    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.touch()
    print("اكتمل الترحيل. لن يعمل السكربت مرة أخرى إلا بـ --force.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
