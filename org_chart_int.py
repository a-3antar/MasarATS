"""ينشئ جداول الهيكل التنظيمي (departments, positions) إن لم تكن موجودة. شغّله مرة واحدة:

    python migrate_organization_tables.py
"""

from database.database import init_db


def main() -> None:
    init_db()
    print("تم التأكد من وجود جداول departments و positions.")


if __name__ == "__main__":
    main()