"""ثوابت مشتركة عبر التطبيق - بدل نشر الأرقام والقيم الثابتة داخل الكود (no magic numbers)."""

ALLOWED_CV_EXTENSIONS: set[str] = {".pdf", ".docx", ".txt"}
MAX_CV_FILE_SIZE_MB: int = 10

# أوزان المطابقة الافتراضية (يمكن تعديلها لاحقاً لكل وظيفة على حدة)
DEFAULT_MATCH_WEIGHTS: dict[str, float] = {
    "skills": 0.5,
    "experience": 0.3,
    "location": 0.1,
    "education": 0.1,
}

JOB_STATUSES: list[str] = ["Draft", "Open", "On Hold", "Closed"]
APPLICATION_STATUSES: list[str] = [
    "New", "Screening", "Shortlisted", "Interview", "Offer", "Hired", "Rejected",
]
