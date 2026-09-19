"""
سكربت لمسح كل المرشحين والتقديمات (applications) فقط، مع الإبقاء على حسابات
المستخدمين والوظائف كما هي. شغّله مرة واحدة من جذر المشروع:

    python reset_candidates.py
"""

from database.database import get_db_session
from models.application import Application
from models.candidate import Candidate


def main() -> None:
    with get_db_session() as session:
        deleted_apps = session.query(Application).delete()
        deleted_candidates = session.query(Candidate).delete()
    print(f"تم حذف {deleted_candidates} مرشح و {deleted_apps} تقديم.")


if __name__ == "__main__":
    main()
