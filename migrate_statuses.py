"""يحوّل حالات المرشحين القديمة إلى مراحل خط التوظيف الجديدة. شغّله مرة واحدة: python migrate_statuses.py"""

from database.database import get_db_session
from models.candidate import Candidate

_LEGACY_MAP = {"Screened": "Screening", "Offered": "Offer"}


def main() -> None:
    with get_db_session() as session:
        for old, new in _LEGACY_MAP.items():
            count = session.query(Candidate).filter(Candidate.status == old).update({"status": new})
            print(f"{old} -> {new}: {count}")


if __name__ == "__main__":
    main()
    