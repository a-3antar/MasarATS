"""خدمة الصفحة الرئيسية: مسار التوظيف وقائمة «تحتاج انتباهك» من بيانات القاعدة الفعلية فقط.
تعيد استخدام ReportService (المؤشرات) و OfferService (العروض) بدل تكرار منطقهما."""

from dataclasses import dataclass

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from core.constants import MATCH_HIGH_THRESHOLD, OFFER_STATUSES
from models.application import Application
from models.candidate import Candidate
from models.interview import Interview
from models.job import Job
from services.offer_service import EXPIRED, EXPIRING_SOON, OfferService
from services.report_service import ReportService

_NEW, _REJECTED, _HIRED, _OPEN_JOB = "New", "Rejected", "Hired", "Open"
_IN_PROGRESS, _COMPLETED = "In Progress", "Completed"
_OFFER_DRAFT, _OFFER_SENT, _OFFER_ACCEPTED, *_ = OFFER_STATUSES

# (عنوان المرحلة، حالة المرشح) - «السير الذاتية» تُضاف في البداية كإجمالي المرشحين
_PIPELINE_STAGES = (
    ("الفرز", "Screening"),
    ("القائمة المختصرة", "Shortlisted"),
    ("المقابلة", "Interview"),
    ("العرض", "Offer"),
    ("التعيين", "Hired"),
)


@dataclass(frozen=True)
class AttentionItem:
    """عنصر يحتاج إجراءً من المستخدم، مع الصفحة التي تعالجه (target = مفتاح صفحة التنقل)."""

    icon: str
    message: str
    count: int
    target: str
    action_label: str


class HomeService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _count(self, stmt) -> int:
        return self._session.scalar(stmt) or 0

    def overview(self) -> dict:
        """كل بيانات الصفحة الرئيسية كأنواع بسيطة قابلة للتخزين في كاش Streamlit."""
        kpis = ReportService(self._session).kpis()
        total_jobs = self._count(select(func.count()).select_from(Job))
        total_applications = self._count(select(func.count()).select_from(Application))
        # تقدم الإعداد مشتق من البيانات نفسها (لا حالة محفوظة): تختفي القائمة عند اكتمال الخطوات
        setup = {
            "candidates": kpis["total_candidates"] > 0,
            "jobs": total_jobs > 0,
            "matched": total_applications > 0,
        }
        return {
            "kpis": kpis,
            "pipeline": self._pipeline(kpis["total_candidates"]),
            "attention": [item for item in self._attention_items() if item is not None],
            "setup": setup,
            "is_new_workspace": not setup["candidates"] and not setup["jobs"],
        }

    # ------------------------------------------------------------ مسار التوظيف

    def _pipeline(self, total_candidates: int) -> list[tuple[str, int]]:
        """عدد المرشحين في كل مرحلة حالياً (حالة المرشح مشتقة من تقديماته)."""
        rows = dict(
            self._session.execute(select(Candidate.status, func.count()).group_by(Candidate.status)).all()
        )
        return [("السير الذاتية", total_candidates)] + [
            (label, rows.get(status, 0)) for label, status in _PIPELINE_STAGES
        ]

    # ------------------------------------------------------------ تحتاج انتباهك

    def _attention_items(self) -> list[AttentionItem | None]:
        return [
            self._candidates_waiting_review(),
            self._strong_without_interview(),
            self._interviews_to_evaluate(),
            self._offers_needing_action(),
        ]

    def _candidates_waiting_review(self) -> AttentionItem | None:
        count = self._count(
            select(func.count()).select_from(Candidate).where(
                or_(Candidate.status == _NEW, Candidate.status.is_(None))
            )
        )
        if not count:
            return None
        return AttentionItem("👥", f"{count} مرشح بانتظار المراجعة", count, "candidates", "مراجعة المرشحين")

    def _strong_without_interview(self) -> AttentionItem | None:
        """تقديمات عالية المطابقة على وظائف مفتوحة ولم تُجدول لها أي مقابلة."""
        no_interview = ~exists().where(Interview.application_id == Application.id)
        open_jobs = select(Job.id).where(Job.status == _OPEN_JOB)
        count = self._count(
            select(func.count()).select_from(Application).where(
                Application.match_score >= MATCH_HIGH_THRESHOLD,
                Application.status.not_in((_REJECTED, _HIRED)),
                Application.job_id.in_(open_jobs),
                no_interview,
            )
        )
        if not count:
            return None
        message = f"{count} مرشح بمطابقة {MATCH_HIGH_THRESHOLD:g}% فأكثر لوظائف مفتوحة بلا مقابلة"
        return AttentionItem("🎯", message, count, "matching", "عرض الأنسب")

    def _interviews_to_evaluate(self) -> AttentionItem | None:
        """مقابلات جارية، أو منتهية بلا تقييم نهائي."""
        count = self._count(
            select(func.count()).select_from(Interview).where(
                or_(
                    Interview.status == _IN_PROGRESS,
                    (Interview.status == _COMPLETED) & Interview.overall_score.is_(None),
                )
            )
        )
        if not count:
            return None
        return AttentionItem("🗓️", f"{count} مقابلة تحتاج تقييماً", count, "interviews", "فتح المقابلات")

    def _offers_needing_action(self) -> AttentionItem | None:
        offers = OfferService(self._session).list_offers()
        drafts = sum(1 for o in offers if o["status"] == _OFFER_DRAFT)
        deadline = sum(1 for o in offers if o["display_status"] in (EXPIRING_SOON, EXPIRED))
        to_hire = sum(1 for o in offers if o["status"] == _OFFER_ACCEPTED and o["app_status"] != _HIRED)

        parts = [
            f"{n} {label}"
            for n, label in ((drafts, "مسودة لم تُرسل"), (deadline, "قاربت مهلتها أو انتهت"), (to_hire, "مقبولة بانتظار التعيين"))
            if n
        ]
        if not parts:
            return None
        count = drafts + deadline + to_hire
        return AttentionItem("📨", "عروض تحتاج إجراء: " + "، ".join(parts), count, "offers", "فتح العروض")
