"""البحث الذكي: الذكاء الاصطناعي يحوّل الطلب إلى فلاتر فقط، والتنفيذ والترتيب بكود ثابت قابل للتفسير."""

import re

from sqlalchemy.orm import Session

from ai.schemas import CandidateSearchFilters
from core.constants import SEARCH_MAX_CANDIDATES
from matching.skill_normalizer import canonical_skill_set, has_skill
from models.candidate import Candidate
from repositories.candidate_repository import CandidateRepository


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _role_matches(role: str, title: str | None) -> bool:
    """كل كلمات المسمى المطلوب موجودة في المسمى (Production Manager ⊂ Senior Production Manager)."""
    tokens = re.findall(r"\w+", _norm(role))
    title_text = _norm(title)
    return bool(tokens) and bool(title_text) and all(t in title_text for t in tokens)


class SearchService:
    def __init__(self, session: Session) -> None:
        self._candidates = CandidateRepository(session)

    @staticmethod
    def parse_query(query: str) -> CandidateSearchFilters:
        """يحوّل النص الحر إلى فلاتر عبر Gemini. يرفع AIServiceError إن لم يتوفر الذكاء الاصطناعي."""
        from ai.gemini_service import GeminiService

        return GeminiService().parse_search_query(query)

    def search(self, filters: CandidateSearchFilters) -> list[dict]:
        """يرجع [{candidate, relevance, reasons}] مرتبة حسب الصلة."""
        results = []
        for candidate in self._candidates.list_all(limit=SEARCH_MAX_CANDIDATES):
            evaluation = self._evaluate(candidate, filters)
            if evaluation is not None:
                results.append({"candidate": candidate, **evaluation})
        results.sort(key=lambda r: r["relevance"], reverse=True)
        return results

    @staticmethod
    def _evaluate(candidate: Candidate, f: CandidateSearchFilters) -> dict | None:
        reasons: list[str] = []
        years = candidate.total_experience_years

        # فلاتر صارمة
        if f.experience_min is not None:
            if years is None or years < f.experience_min:
                return None
            reasons.append(f"خبرة {years:g} سنة")
        if f.experience_max is not None and years is not None and years > f.experience_max:
            return None
        if f.location:
            if _norm(f.location) not in _norm(candidate.location):
                return None
            reasons.append(f"الموقع: {candidate.location}")

        # معايير مرنة: نسبة تحقق كل معيار
        soft_total, soft_hits = 0, 0.0

        if f.role:
            soft_total += 1
            titles = [candidate.current_position, *(candidate.previous_positions or [])]
            if any(_role_matches(f.role, t) for t in titles):
                soft_hits += 1
                reasons.append(f"مسمى مطابق: {f.role}")

        if f.industry:
            soft_total += 1
            wanted = _norm(f.industry)
            if any(_norm(i) and (wanted in _norm(i) or _norm(i) in wanted) for i in candidate.industries or []):
                soft_hits += 1
                reasons.append(f"مجال: {f.industry}")

        if f.skills:
            soft_total += 1
            keys = canonical_skill_set(candidate.all_skills)
            matched = [s for s in f.skills if has_skill(s, keys)]
            soft_hits += len(matched) / len(f.skills)
            if matched:
                reasons.append("مهارات: " + ", ".join(matched))

        if soft_total and soft_hits == 0:
            return None
        relevance = round(soft_hits / soft_total * 100, 1) if soft_total else 100.0
        return {"relevance": relevance, "reasons": reasons}
    