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
        self._engine = self._build_engine()

    @staticmethod
    def _build_engine():
        """Hybrid (قواعد + دلالي) إن توفر GEMINI_API_KEY، وإلا Rule-based فقط - نفس نمط
        fallback المتبع في بقية المشروع عند غياب مفتاح الذكاء الاصطناعي."""
        from config.settings import get_settings

        settings = get_settings()
        if settings.gemini_api_key or settings.alt_gemini_api_key:
            from matching.hybrid_engine import HybridMatchingEngine
            return HybridMatchingEngine()
        return RuleBasedMatchingEngine()

    def match_all_candidates_to_job(self, job: Job, candidates: list[Candidate]) -> list[dict]:
        """يحسب درجة مطابقة كل المرشحين لوظيفة واحدة، ويحفظها كسجل application، ويرجع النتائج مرتبة."""
        if hasattr(self._engine, "warm_up_candidates"):
            self._engine.warm_up_candidates(candidates, job)

        results = []
        for candidate in candidates:
            result = self._engine.calculate_match(candidate, job)
            application = self._save_or_update_application(candidate.id, job.id, result)
            results.append({"candidate": candidate, "application": application, **result})

        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    def match_candidate_to_all_jobs(self, candidate: Candidate, jobs: list[Job]) -> list[dict]:
        """يحسب درجة مطابقة مرشح واحد مقابل كل الوظائف المعطاة، ويحفظها كسجل application، ويرجع النتائج مرتبة."""
        if hasattr(self._engine, "warm_up_jobs"):
            self._engine.warm_up_jobs(candidate, jobs)

        results = []
        for job in jobs:
            result = self._engine.calculate_match(candidate, job)
            application = self._save_or_update_application(candidate.id, job.id, result)
            results.append({"job": job, "application": application, **result})

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

    def top_jobs_for_candidate(self, candidate: Candidate, jobs: list[Job], limit: int = 5) -> list[dict]:
        """أفضل الوظائف لمرشح واحد للعرض فقط (لا تحفظ سجلات application)."""
        if hasattr(self._engine, "warm_up_jobs"):
            self._engine.warm_up_jobs(candidate, jobs)

        results = [{"job": job, **self._engine.calculate_match(candidate, job)} for job in jobs]
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    def rank_jobs_for_candidate(self, candidate: Candidate, jobs: list[Job]) -> list[dict]:
        """يرتّب الوظائف حسب مطابقتها لمرشح واحد بدون حفظ أي شيء في القاعدة (للعرض فقط)."""
        if hasattr(self._engine, "warm_up_jobs"):
            self._engine.warm_up_jobs(candidate, jobs)

        results = [{"job": job, **self._engine.calculate_match(candidate, job)} for job in jobs]
        results.sort(key=lambda r: r["score"], reverse=True)
        return results