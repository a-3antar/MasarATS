"""خدمة التقارير: تجميع أرقام لوحة المعلومات والتقارير. ترجع بيانات بسيطة (dict/list) قابلة للتخزين في كاش Streamlit."""

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.constants import (
    APPLICATION_STATUSES,
    DASHBOARD_TOP_SKILLS,
    MIN_CANDIDATES_PER_JOB,
    NEW_CV_DAYS,
    QUALIFIED_SCORE_THRESHOLD,
    SEARCH_MAX_CANDIDATES,
)
from matching.skill_normalizer import canonical_skill, canonical_skill_set, has_skill
from models.application import Application
from models.candidate import Candidate
from models.interview import Interview
from models.job import Job

UNSPECIFIED_DEPARTMENT = "غير محدد"
UNANALYZED_LEVEL = "غير محلَّل"
_REJECTED = "Rejected"
# مراحل القمع بالترتيب (بدون Rejected)
_FUNNEL_STAGES = [s for s in APPLICATION_STATUSES if s != _REJECTED]


def department_of(job: Job) -> str:
    """القسم الذي تنتمي له الوظيفة. نقطة التحويل الوحيدة عند ربط الأقسام بجدول departments (المرحلة 4)."""
    return (job.department or "").strip() or UNSPECIFIED_DEPARTMENT


class ReportService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _count(self, stmt) -> int:
        return self._session.scalar(stmt) or 0

    def _candidates_with_status(self, status: str) -> int:
        return self._count(select(func.count()).select_from(Candidate).where(Candidate.status == status))

    # ------------------------------------------------------------ المؤشرات

    def kpis(self) -> dict[str, int]:
        # SQLite يخزّن UTC بدون tzinfo، فنقارن بتاريخ UTC بدون tzinfo
        since = (datetime.now(timezone.utc) - timedelta(days=NEW_CV_DAYS)).replace(tzinfo=None)
        return {
            "total_candidates": self._count(select(func.count()).select_from(Candidate)),
            "open_jobs": self._count(select(func.count()).select_from(Job).where(Job.status == "Open")),
            "scheduled_interviews": self._count(
                select(func.count()).select_from(Interview).where(Interview.status == "Scheduled")
            ),
            "new_cvs": self._count(select(func.count()).select_from(Candidate).where(Candidate.created_at >= since)),
            "shortlisted": self._candidates_with_status("Shortlisted"),
            "offers": self._candidates_with_status("Offer"),
            "hired": self._candidates_with_status("Hired"),
        }

    # ------------------------------------------------------------ التقديمات والقمع

    def applications_by_status(self) -> dict[str, int]:
        rows = self._session.execute(
            select(Application.status, func.count()).group_by(Application.status)
        ).all()
        counts = {status: 0 for status in APPLICATION_STATUSES}
        for status, total in rows:
            counts[status if status in counts else APPLICATION_STATUSES[0]] += total
        return counts

    def funnel(self) -> list[tuple[str, int]]:
        """قمع تراكمي: كل مرحلة = التقديمات التي وصلت لها أو تجاوزتها (المرفوضون لا يُحسبون)."""
        counts = self.applications_by_status()
        result = []
        for index, stage in enumerate(_FUNNEL_STAGES):
            result.append((stage, sum(counts[s] for s in _FUNNEL_STAGES[index:])))
        return result

    # ------------------------------------------------------------ المرشحون

    def candidates_by_career_level(self) -> dict[str, int]:
        levels = Counter()
        for (analysis,) in self._session.execute(select(Candidate.ai_analysis)):
            level = ((analysis or {}).get("career_level") or "").strip()
            levels[level or UNANALYZED_LEVEL] += 1
        return dict(levels.most_common())

    def candidates_by_department(self) -> dict[str, int]:
        """عدد المرشحين المتقدمين لكل قسم (حسب قسم الوظيفة التي قُدِّم عليها)."""
        rows = self._session.execute(
            select(Job, func.count(func.distinct(Application.candidate_id)))
            .join(Application, Application.job_id == Job.id)
            .group_by(Job.id)
        ).all()
        totals = Counter()
        for job, total in rows:
            totals[department_of(job)] += total
        return dict(totals.most_common())

    def top_skills(self, limit: int = DASHBOARD_TOP_SKILLS) -> list[tuple[str, int]]:
        """أكثر المهارات تكراراً بين المرشحين (مهارة مرة واحدة لكل مرشح، بعد توحيد الاسم)."""
        counts: Counter[str] = Counter()
        names: dict[str, Counter[str]] = {}
        stmt = select(
            Candidate.technical_skills, Candidate.computer_skills, Candidate.managerial_skills,
            Candidate.soft_skills, Candidate.skills,
        ).limit(SEARCH_MAX_CANDIDATES)
        for row in self._session.execute(stmt):
            per_candidate: dict[str, str] = {}
            for group in row:
                for skill in group or []:
                    key = canonical_skill(skill)
                    if key:
                        per_candidate.setdefault(key, skill.strip())
            for key, display in per_candidate.items():
                counts[key] += 1
                names.setdefault(key, Counter())[display] += 1
        return [(names[key].most_common(1)[0][0], total) for key, total in counts.most_common(limit)]

    def top_matches(self, limit: int = 5) -> list[dict]:
        rows = self._session.execute(
            select(Candidate.full_name, Candidate.current_position, Job.title, Application.match_score)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
            .where(Application.match_score.is_not(None))
            .order_by(Application.match_score.desc())
            .limit(limit)
        ).all()
        return [
            {"name": name, "position": position or "-", "job": title, "score": score}
            for name, position, title, score in rows
        ]

    # ------------------------------------------------------------ الوظائف

    def jobs_needing_candidates(self, minimum: int = MIN_CANDIDATES_PER_JOB) -> list[dict]:
        """وظائف مفتوحة عدد المرشحين المطابَقين لها أقل من الحد الأدنى."""
        rows = self._session.execute(
            select(Job, func.count(Application.id))
            .outerjoin(Application, Application.job_id == Job.id)
            .where(Job.status == "Open")
            .group_by(Job.id)
        ).all()
        result = [
            {"job": job.title, "department": department_of(job), "candidates": total}
            for job, total in rows if total < minimum
        ]
        return sorted(result, key=lambda r: r["candidates"])

    def required_skills_availability(self, limit: int = 15) -> list[dict]:
        """لكل مهارة مطلوبة في الوظائف المفتوحة: كم مرشحاً يملكها (الأقل توفراً أولاً)."""
        jobs = self._session.scalars(select(Job).where(Job.status == "Open")).all()
        demand: Counter[str] = Counter()
        display: dict[str, str] = {}
        for job in jobs:
            for skill in job.all_required_skills:
                key = canonical_skill(skill)
                if key:
                    demand[key] += 1
                    display.setdefault(key, skill)
        if not demand:
            return []

        candidate_sets = [
            canonical_skill_set(Candidate.all_skills.fget(c))
            for c in self._session.scalars(select(Candidate).limit(SEARCH_MAX_CANDIDATES))
        ]
        rows = [
            {
                "skill": display[key],
                "jobs_requiring": demand[key],
                "candidates_with_skill": sum(1 for keys in candidate_sets if has_skill(display[key], keys)),
            }
            for key in demand
        ]
        rows.sort(key=lambda r: (r["candidates_with_skill"], -r["jobs_requiring"]))
        return rows[:limit]

    # ------------------------------------------------------------ تقرير وظيفة

    def recruitment_report(self, job_id: int) -> dict[str, int]:
        """قمع وظيفة واحدة: السير، المؤهلون، القائمة المختصرة، المقابلات، العروض، التعيين."""
        applications = self._session.scalars(select(Application).where(Application.job_id == job_id)).all()
        index = {s: i for i, s in enumerate(APPLICATION_STATUSES)}

        def reached(stage: str) -> int:
            return sum(1 for a in applications if a.status != _REJECTED and index.get(a.status, 0) >= index[stage])

        interviewed_ids = set(
            self._session.scalars(
                select(Interview.application_id).where(
                    Interview.application_id.in_([a.id for a in applications] or [0])
                )
            )
        )
        interviewed = sum(1 for a in applications if a.id in interviewed_ids or a.status in ("Interview", "Offer", "Hired"))
        return {
            "total_cvs": len(applications),
            "qualified": sum(1 for a in applications if (a.match_score or 0) >= QUALIFIED_SCORE_THRESHOLD),
            "shortlisted": reached("Shortlisted"),
            "interviewed": interviewed,
            "offers": reached("Offer"),
            "hired": reached("Hired"),
        }
