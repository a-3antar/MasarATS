"""خدمة المطابقة: تشغّل محرك المطابقة وتحفظ (أو تحدّث) نتائج التقديم القابلة للتفسير."""

from sqlalchemy.orm import Session

from matching.rule_engine import RuleBasedMatchingEngine
from models.application import Application
from models.candidate import Candidate
from models.job import Job
from repositories.application_repository import ApplicationRepository


class MatchingService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._applications = ApplicationRepository(session)
        self._engine = RuleBasedMatchingEngine()

    def match_all_candidates_to_job(self, job: Job, candidates: list[Candidate]) -> list[dict]:
        """يحسب درجة المطابقة لكل مرشح مقابل وظيفة معينة، ويحفظها كسجل application، ويرجع النتائج مرتبة."""
        results = []
        for candidate in candidates:
            result = self._engine.calculate_match(candidate, job)
            self._save_or_update_application(candidate.id, job.id, result)
            results.append({"candidate": candidate, **result})

        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    def _save_or_update_application(self, candidate_id: int, job_id: int, result: dict) -> Application:
        application = self._applications.get_existing(candidate_id, job_id)
        if application is None:
            application = Application(candidate_id=candidate_id, job_id=job_id)
            self._applications.add(application)

        application.match_score = result["score"]
        application.match_breakdown = {
            "breakdown": result["breakdown"],
            "strengths": result["strengths"],
            "gaps": result["gaps"],
        }
        return application
