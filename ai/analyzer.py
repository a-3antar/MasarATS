"""تحليل شامل للمرشح عبر Gemini: مستوى وظيفي، نقاط قوة، فجوات محتملة، ووظائف مناسبة - بناءً على بيانات السيرة الفعلية فقط."""

from ai.schemas import CandidateAnalysis
from models.candidate import Candidate


def candidate_context(candidate: Candidate) -> str:
    """نص بيانات المرشح المُرسل للنموذج. يُستخدم أيضاً لحساب input_hash للكاش."""
    parts = [f"الاسم: {candidate.full_name}"]
    if candidate.current_position:
        parts.append(f"المسمى الحالي: {candidate.current_position}")
    if candidate.total_experience_years is not None:
        parts.append(f"سنوات الخبرة: {candidate.total_experience_years}")
    if candidate.all_skills:
        parts.append("المهارات: " + ", ".join(candidate.all_skills))
    if candidate.industries:
        parts.append("مجالات العمل: " + ", ".join(candidate.industries))
    if candidate.summary:
        parts.append(f"النبذة: {candidate.summary}")
    for item in candidate.experience or []:
        heading = " — ".join(p for p in (item.get("position"), item.get("company")) if p)
        responsibilities = "؛ ".join(item.get("responsibilities") or [])
        if heading or responsibilities:
            parts.append(f"خبرة: {heading} — {responsibilities}")
    for item in candidate.education or []:
        line = " — ".join(p for p in (item.get("degree"), item.get("major"), item.get("institution")) if p)
        if line:
            parts.append(f"تعليم: {line}")
    return "\n".join(parts)


def analyze_candidate(context: str) -> CandidateAnalysis:
    """يولّد تحليل الذكاء الاصطناعي من نص بيانات المرشح الجاهز. يرفع AIServiceError عند الفشل."""
    from ai.gemini_service import GeminiService

    return GeminiService().analyze_candidate(context)