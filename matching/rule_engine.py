"""
محرك مطابقة بسيط قائم على القواعد (Rule-based) فقط - بلا أي فهم دلالي (semantic).
هذا يكفي للنسخة الأولى البسيطة، ويمكن استبداله لاحقاً بـ HybridEngine الذي
يضيف مطابقة دلالية عبر AI دون تغيير أي كود يستدعي MatchingEngine.
"""

from typing import Any

from core.constants import DEFAULT_MATCH_WEIGHTS
from matching.base import MatchingEngine
from models.candidate import Candidate
from models.job import Job


def _normalize(value: str) -> str:
    return value.strip().lower()


class RuleBasedMatchingEngine(MatchingEngine):
    """يحسب درجة مطابقة مفسَّرة (explainable) بين مرشح ووظيفة."""

    def calculate_match(self, candidate: Candidate, job: Job) -> dict[str, Any]:
        weights = job.match_weights or DEFAULT_MATCH_WEIGHTS

        skills_score, matched_skills, missing_skills = self._score_skills(candidate, job)
        experience_score = self._score_experience(candidate, job)
        location_score = self._score_location(candidate, job)
        education_score = self._score_education(candidate, job)

        breakdown = {
            "skills": round(skills_score, 1),
            "experience": round(experience_score, 1),
            "location": round(location_score, 1),
            "education": round(education_score, 1),
        }

        total = sum(breakdown[key] * weights.get(key, 0) for key in breakdown)
        total = round(min(total, 100.0), 1)

        strengths = [f"✓ مهارة متطابقة: {s}" for s in matched_skills]
        if experience_score >= 80:
            strengths.append(f"✓ خبرة كافية ({candidate.total_experience_years or 0} سنة)")

        gaps = [f"⚠ مهارة غير موثّقة صراحة في السيرة الذاتية: {s}" for s in missing_skills]
        if experience_score < 50:
            gaps.append("⚠ الخبرة المذكورة أقل من المطلوب للوظيفة")

        return {
            "score": total,
            "breakdown": breakdown,
            "strengths": strengths,
            "gaps": gaps,
        }

    @staticmethod
    def _score_skills(candidate: Candidate, job: Job) -> tuple[float, list[str], list[str]]:
        required = [_normalize(s) for s in (job.required_skills or [])]
        candidate_skills = {_normalize(s) for s in candidate.all_skills}

        if not required:
            return 100.0, [], []

        matched = [s for s in required if s in candidate_skills]
        missing = [s for s in required if s not in candidate_skills]
        score = (len(matched) / len(required)) * 100
        return score, matched, missing

    @staticmethod
    def _score_experience(candidate: Candidate, job: Job) -> float:
        required = job.required_experience_years
        actual = candidate.total_experience_years

        if not required or required <= 0:
            return 100.0
        if actual is None:
            return 0.0
        return min((actual / required) * 100, 100.0)

    @staticmethod
    def _score_location(candidate: Candidate, job: Job) -> float:
        if not job.location:
            return 100.0
        if not candidate.location:
            return 50.0  # غير معروف - لا نعاقب المرشح كلياً
        return 100.0 if _normalize(job.location) in _normalize(candidate.location) else 40.0

    @staticmethod
    def _score_education(candidate: Candidate, job: Job) -> float:
        # مبسّطة جداً في هذه المرحلة: وجود أي سجل تعليمي يكفي
        return 100.0 if candidate.education else 60.0
