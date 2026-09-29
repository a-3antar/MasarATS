"""إحصاءات صفحة الوظائف: مؤشرات، قمع، توزيع المطابقة، وتحليل مهارات وظيفة واحدة.
كله بكود ثابت وقابل للتفسير (بدون استدعاء Gemini). ترجع dataclasses بسيطة قابلة للتخزين في كاش Streamlit."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, defer

from core.constants import (
    APPLICATION_STATUSES,
    DEFAULT_VACANCIES,
    JOB_INSIGHT_MAX_SKILLS,
    JOB_NEW_DAYS,
    JOB_TREND_WEEKS,
    MATCH_HIGH_THRESHOLD,
    MATCH_MEDIUM_THRESHOLD,
    MIN_CANDIDATES_PER_JOB,
    QUALIFIED_SCORE_THRESHOLD,
    SKILL_GAP_COVERAGE,
    SKILL_STRONG_COVERAGE,
)
from core.exceptions import ValidationError
from matching.skill_normalizer import canonical_skill_set, has_skill
from models.application import Application
from models.candidate import Candidate
from models.job import Job

_REJECTED = "Rejected"
_STATUS_INDEX = {status: i for i, status in enumerate(APPLICATION_STATUSES)}
_DAYS_PER_WEEK = 7


@dataclass(frozen=True)
class JobStats:
    """أرقام قمع وظيفة واحدة (المتقدمون = المرشحون المطابَقون فعلاً)."""

    applicants: int = 0
    qualified: int = 0
    shortlisted: int = 0
    interviewed: int = 0
    offers: int = 0
    hired: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0

    def funnel(self) -> list[tuple[str, int]]:
        return [
            ("المرشحون", self.applicants), ("مؤهلون", self.qualified),
            ("قائمة مختصرة", self.shortlisted), ("مقابلة", self.interviewed), ("عرض", self.offers),
        ]


@dataclass(frozen=True)
class JobInsight:
    stats: JobStats
    top_skills: list[str] = field(default_factory=list)
    gap_skills: list[str] = field(default_factory=list)
    quick: list[str] = field(default_factory=list)


def _naive_utc(value: datetime) -> datetime:
    """SQLite يعيد التاريخ بدون tzinfo؛ نوحّد المقارنة على UTC بدون tzinfo."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


class JobInsightsService:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------ المؤشرات العامة

    def kpis(self) -> dict:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        month_ago = now - timedelta(days=JOB_NEW_DAYS)
        created = self._session.execute(select(Job.status, Job.created_at)).all()

        def trend(status: str) -> list[int]:
            buckets = [0] * JOB_TREND_WEEKS
            for job_status, created_at in created:
                weeks_ago = (now - _naive_utc(created_at)).days // _DAYS_PER_WEEK
                if job_status == status and 0 <= weeks_ago < JOB_TREND_WEEKS:
                    buckets[JOB_TREND_WEEKS - 1 - weeks_ago] += 1
            return buckets

        def new_this_month(status: str) -> int:
            return sum(1 for s, c in created if s == status and _naive_utc(c) >= month_ago)

        needed = self._session.scalar(
            select(func.coalesce(func.sum(func.coalesce(Job.vacancies, DEFAULT_VACANCIES)), 0))
            .where(Job.status == "Open")
        ) or 0

        from services.report_service import ReportService

        return {
            "open_jobs": sum(1 for s, _ in created if s == "Open"),
            "open_new_month": new_this_month("Open"),
            "open_trend": trend("Open"),
            "draft_jobs": sum(1 for s, _ in created if s == "Draft"),
            "draft_new_month": new_this_month("Draft"),
            "draft_trend": trend("Draft"),
            "candidates_needed": int(needed),
            "jobs_needing_candidates": len(ReportService(self._session).jobs_needing_candidates()),
        }

    # ------------------------------------------------------------ إحصاءات لكل وظيفة

    def stats_by_job(self) -> dict[int, JobStats]:
        """استعلامان مجمّعان لكل الوظائف دفعة واحدة (بدون N+1)."""
        score = Application.match_score
        score_rows = self._session.execute(
            select(
                Application.job_id,
                func.count(),
                func.sum(case((score >= QUALIFIED_SCORE_THRESHOLD, 1), else_=0)),
                func.sum(case((score >= MATCH_HIGH_THRESHOLD, 1), else_=0)),
                func.sum(case(((score >= MATCH_MEDIUM_THRESHOLD) & (score < MATCH_HIGH_THRESHOLD), 1), else_=0)),
            ).group_by(Application.job_id)
        ).all()

        reached: dict[int, dict[str, int]] = {}
        status_rows = self._session.execute(
            select(Application.job_id, Application.status, func.count()).group_by(Application.job_id, Application.status)
        ).all()
        for job_id, status, total in status_rows:
            if status == _REJECTED:
                continue
            level = _STATUS_INDEX.get(status, 0)
            counters = reached.setdefault(job_id, {})
            for stage in ("Shortlisted", "Interview", "Offer", "Hired"):
                if level >= _STATUS_INDEX[stage]:
                    counters[stage] = counters.get(stage, 0) + total

        result: dict[int, JobStats] = {}
        for job_id, total, qualified, high, medium in score_rows:
            counters = reached.get(job_id, {})
            high, medium = int(high or 0), int(medium or 0)
            result[job_id] = JobStats(
                applicants=total, qualified=int(qualified or 0),
                shortlisted=counters.get("Shortlisted", 0), interviewed=counters.get("Interview", 0),
                offers=counters.get("Offer", 0), hired=counters.get("Hired", 0),
                high=high, medium=medium, low=max(total - high - medium, 0),
            )
        return result

    # ------------------------------------------------------------ تحليل وظيفة واحدة

    def job_insight(self, job_id: int) -> JobInsight:
        job = self._session.get(Job, job_id)
        if job is None:
            raise ValidationError("الوظيفة غير موجودة.")
        stats = self.stats_by_job().get(job_id, JobStats())
        coverage = self._skill_coverage(job)

        ranked = sorted(coverage.items(), key=lambda item: item[1], reverse=True)
        top = [s for s, ratio in ranked if ratio >= SKILL_STRONG_COVERAGE][:JOB_INSIGHT_MAX_SKILLS]
        gaps = [s for s, ratio in reversed(ranked) if ratio < SKILL_GAP_COVERAGE][:JOB_INSIGHT_MAX_SKILLS]
        return JobInsight(stats=stats, top_skills=top, gap_skills=gaps, quick=self._quick_insights(stats, gaps))

    def _skill_coverage(self, job: Job) -> dict[str, float]:
        """نسبة المرشحين الذين توثّق سيرهم كل مهارة مطلوبة (بين المؤهلين إن وُجدوا، وإلا كل المطابَقين)."""
        required = job.all_required_skills
        if not required:
            return {}
        rows = self._session.execute(
            select(Candidate, Application.match_score)
            .join(Application, Application.candidate_id == Candidate.id)
            .where(Application.job_id == job.id)
            .options(defer(Candidate.raw_text), defer(Candidate.embedding))
        ).all()
        pool = [c for c, s in rows if (s or 0) >= QUALIFIED_SCORE_THRESHOLD] or [c for c, _ in rows]
        if not pool:
            return {}
        skill_sets = [canonical_skill_set(c.all_skills) for c in pool]
        return {
            skill: sum(1 for keys in skill_sets if has_skill(skill, keys)) / len(skill_sets)
            for skill in required
        }

    @staticmethod
    def _quick_insights(stats: JobStats, gaps: list[str]) -> list[str]:
        if stats.applicants == 0:
            return ["لم تُشغَّل المطابقة لهذه الوظيفة بعد؛ استخدم صفحة «المطابقة» لتقييم المرشحين."]
        notes = [f"{stats.qualified} من {stats.applicants} مرشحاً مطابَقاً مؤهلون (درجة {QUALIFIED_SCORE_THRESHOLD:g}% فأكثر)."]
        if stats.qualified < MIN_CANDIDATES_PER_JOB:
            notes.append(f"عدد المؤهلين أقل من الحد الأدنى ({MIN_CANDIDATES_PER_JOB}) — تحتاج الوظيفة مصادر مرشحين إضافية.")
        if gaps:
            notes.append(f"مهارة غير موثّقة لدى معظم المرشحين: {gaps[0]} (تحقّق منها في المقابلة).")
        if stats.shortlisted and not stats.interviewed:
            notes.append("لم تُجرَ مقابلات مع القائمة المختصرة بعد.")
        return notes