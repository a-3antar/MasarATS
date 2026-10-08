"""توليد أسئلة مقابلة عبر Gemini بناءً على وصف الوظيفة وسيرة المرشح الفعلية، وتقييم الإجابات."""

from ai.schemas import InterviewQuestions
from models.candidate import Candidate
from models.job import Job


def _job_context(job: Job) -> str:
    parts = [f"المسمى: {job.title}"]
    if job.department:
        parts.append(f"القسم: {job.department}")
    if job.required_experience_years:
        parts.append(f"الخبرة المطلوبة: {job.required_experience_years} سنة")
    if job.all_required_skills:
        parts.append("المهارات المطلوبة: " + ", ".join(job.all_required_skills))
    if job.description:
        parts.append(f"الوصف: {job.description}")
    if job.competency_weights:
        parts.append("الكفاءات المعتمدة: " + ", ".join(job.competency_weights))
    return "\n".join(parts)


def _candidate_context(candidate: Candidate) -> str:
    parts = [f"الاسم: {candidate.full_name}"]
    if candidate.current_position:
        parts.append(f"المسمى الحالي: {candidate.current_position}")
    if candidate.total_experience_years is not None:
        parts.append(f"سنوات الخبرة: {candidate.total_experience_years}")
    if candidate.all_skills:
        parts.append("المهارات: " + ", ".join(candidate.all_skills))
    if candidate.summary:
        parts.append(f"النبذة: {candidate.summary}")
    for item in candidate.experience or []:
        heading = " — ".join(p for p in (item.get("position"), item.get("company")) if p)
        responsibilities = "؛ ".join(item.get("responsibilities") or [])
        if heading or responsibilities:
            parts.append(f"خبرة: {heading} — {responsibilities}")
    return "\n".join(parts)


def generate_interview_questions(candidate: Candidate, job: Job) -> InterviewQuestions:
    """يولّد أسئلة مقابلة مبنية على بيانات الوظيفة والمرشح الفعلية. يرفع AIServiceError عند الفشل."""
    from ai.gemini_service import GeminiService

    return GeminiService().generate_interview_questions(_job_context(job), _candidate_context(candidate))


def evaluate_interview_answer(
    job: Job, question: str, answer: str, prior_qa: list[tuple[str, str]] | None = None
):
    """
    يقيّم إجابة مرشح على سؤال واحد بالنسبة لمتطلبات الوظيفة.
    prior_qa: (سؤال، إجابة) من بقية أسئلة نفس المقابلة، تُستخدم كسياق مرجعي فقط.
    يرفع AIServiceError عند الفشل.
    """
    from ai.gemini_service import GeminiService

    return GeminiService().evaluate_interview_answer(_job_context(job), question, answer, prior_qa or [])

def generate_questions_for_job(job: Job) -> InterviewQuestions:
    """يولّد أسئلة مقابلة عامة للوظيفة بدون مرشح محدد (لبنك الأسئلة). يرفع AIServiceError عند الفشل."""
    from ai.gemini_service import GeminiService

    no_candidate = "لا يوجد مرشح محدد: ولّد أسئلة عامة للوظيفة، واترك cv_specific فارغة."
    return GeminiService().generate_interview_questions(_job_context(job), no_candidate)