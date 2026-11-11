
from typing import Any


from matching.base import MatchingEngine
from models.candidate import Candidate
from models.job import Job
from matching.skill_normalizer import canonical_skill_set, has_skill
from core.constants import (
    CAREER_LEVELS, 
    DEFAULT_MATCH_WEIGHTS, 
    OVERQ_EXP_MIN_EXTRA_YEARS, 
    OVERQ_EXP_RATIO,
    OVERQ_HIGH_LEVEL_GAP, 
    OVERQ_LEVEL_GAP,
)


def _normalize(value: str) -> str:
    return value.strip().lower()

_LEVEL_ORDER = sorted(
    ((name.lower(), i) for i, name in enumerate(CAREER_LEVELS)), key=lambda kv: -len(kv[0])
)


def _level_index(text: str | None) -> int | None:
    value = (text or "").strip().lower()
    return next((i for name, i in _LEVEL_ORDER if name in value), None) if value else None


def assess_overqualification(candidate: Candidate, job: Job) -> dict[str, Any]:
    reasons: list[str] = []
    severity = 0

    required, actual = job.required_experience_years, candidate.total_experience_years
    if required and required > 0 and actual is not None:
        if actual / required >= OVERQ_EXP_RATIO and actual - required >= OVERQ_EXP_MIN_EXTRA_YEARS:
            reasons.append(f"خبرة المرشح {actual:g} سنة مقابل {required:g} مطلوبة")
            severity += 1

    cand_level = _level_index((candidate.ai_analysis or {}).get("career_level"))
    job_level = _level_index(job.career_level)
    if cand_level is not None and job_level is not None and cand_level - job_level >= OVERQ_LEVEL_GAP:
        reasons.append(f"مستوى المرشح ({CAREER_LEVELS[cand_level]}) أعلى من مستوى الوظيفة ({CAREER_LEVELS[job_level]})")
        severity += 2 if cand_level - job_level >= OVERQ_HIGH_LEVEL_GAP else 1

    level = "none" if severity == 0 else "moderate" if severity == 1 else "high"
    return {"level": level, "reasons": reasons}

class RuleBasedMatchingEngine(MatchingEngine):

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

        wanted_industries = {_normalize(i) for i in (job.preferred_industries or [])}
        for industry in candidate.industries or []:
            if _normalize(industry) in wanted_industries:
                strengths.append(f"✓ خبرة سابقة في المجال: {industry}")

        gaps = [f"⚠غير موثّقة: {s}" for s in missing_skills]
        if experience_score < 50:
            gaps.append("⚠ الخبرة المذكورة أقل من المطلوب للوظيفة")

        return {
            "score": total,
            "breakdown": breakdown,
            "strengths": strengths,
            "gaps": gaps,
            "overqualified": assess_overqualification(candidate, job),
        }

    @staticmethod
    def _score_skills(candidate: Candidate, job: Job) -> tuple[float, list[str], list[str]]:
        required = job.all_required_skills
        if not required:
            return 100.0, [], []

        candidate_keys = canonical_skill_set(candidate.all_skills)
        matched = [s for s in required if has_skill(s, candidate_keys)]
        missing = [s for s in required if s not in matched]
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
            return 50.0
        return 100.0 if _normalize(job.location) in _normalize(candidate.location) else 40.0

    @staticmethod
    def _score_education(candidate: Candidate, job: Job) -> float:
        return 100.0 if candidate.education else 60.0
