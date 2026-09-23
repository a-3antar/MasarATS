"""تحويل وصف وظيفة غير منظم إلى متطلبات مهيكلة عبر Gemini - يُستخدم من صفحة إدارة الوظائف."""

from ai.schemas import JobRequirements


def analyze_job_description(description: str) -> JobRequirements:
    """يحلل نص وصف وظيفة حر ويرجع متطلبات مهيكلة (title, skills, experience...). يرفع AIServiceError عند الفشل."""
    from ai.gemini_service import GeminiService

    return GeminiService().analyze_job_description(description)