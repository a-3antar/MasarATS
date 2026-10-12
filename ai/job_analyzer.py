
from ai.schemas import JobRequirements


def analyze_job_description(description: str) -> JobRequirements:
    from ai.gemini_service import GeminiService

    return GeminiService().analyze_job_description(description)
