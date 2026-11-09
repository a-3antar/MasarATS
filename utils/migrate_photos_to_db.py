"""ترحيل لمرة واحدة: نقل صور المرشحين الموجودة كملفات (uploads/photos) إلى قاعدة البيانات.

التشغيل من جذر المشروع (على جهازك حيث توجد الصور):
    python utils/migrate_photos_to_db.py
    python utils/migrate_photos_to_db.py --force     (إعادة التنفيذ وإعادة كتابة الصور الموجودة في القاعدة)

بعد النجاح يُنشأ ملف علامة فلا يعمل السكربت مرة ثانية إلا بـ --force.
بعد الترحيل ارفع ملف قاعدة البيانات (data/smartats.db) مع المشروع حتى تصل الصور للسيرفر.
"""
import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from config.settings import BASE_DIR  # noqa: E402
from core.logging import get_logger, setup_logging  # noqa: E402
from database.database import get_db_session, init_db  # noqa: E402
from models.candidate import Candidate  # noqa: E402
from models.candidate_photo import CandidatePhoto  # noqa: E402

logger = get_logger("migrate_photos_to_db")

MARKER = BASE_DIR / "data" / ".photos_migrated"


def _is_valid_image(data: bytes) -> bool:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        return True
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="نقل صور المرشحين من الملفات إلى قاعدة البيانات (مرة واحدة).")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    setup_logging()
    if MARKER.exists() and not args.force:
        print("تم تنفيذ الترحيل من قبل. استخدم --force لإعادته.")
        return 0

    init_db()

    migrated = skipped = 0
    missing: list[tuple[int, str]] = []
    invalid: list[tuple[int, str]] = []

    with get_db_session() as session:
        candidates = session.scalars(
            select(Candidate).where(Candidate.photo_path.is_not(None)).order_by(Candidate.id)
        ).all()
        existing_ids = set(session.scalars(select(CandidatePhoto.candidate_id)))
        print(f"مرشحون لديهم مسار صورة: {len(candidates)}")

        for candidate in candidates:
            if candidate.id in existing_ids and not args.force:
                skipped += 1
                continue

            path = BASE_DIR / candidate.photo_path
            if not path.exists():
                missing.append((candidate.id, candidate.photo_path))
                continue

            data = path.read_bytes()
            if not _is_valid_image(data):
                invalid.append((candidate.id, candidate.photo_path))
                continue

            row = session.get(CandidatePhoto, candidate.id)
            if row is None:
                session.add(CandidatePhoto(candidate_id=candidate.id, data=data))
            else:
                row.data = data
            migrated += 1
            print(f"  ✓ مرشح #{candidate.id}: {candidate.photo_path} ({len(data) // 1024} KB)")

    print(f"\nتم نقل: {migrated} | موجودة مسبقاً: {skipped} | ملف غير موجود: {len(missing)} | صورة تالفة: {len(invalid)}")
    if missing:
        print("مرشحون مسار صورتهم موجود لكن الملف مفقود (ارفع صورتهم من جديد من تبويب «تعديل»):")
        for candidate_id, rel in missing:
            print(f"  #{candidate_id}: {rel}")
    if invalid:
        print("ملفات صور تالفة لم تُنقل:")
        for candidate_id, rel in invalid:
            print(f"  #{candidate_id}: {rel}")

    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.touch()
    print("اكتمل الترحيل. لن يعمل السكربت مرة أخرى إلا بـ --force.")
    return 0


if __name__ == "__main__":
    sys.exit(main())