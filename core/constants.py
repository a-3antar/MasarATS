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

# استخراج صورة المرشح من السيرة الذاتية
PHOTOS_SUBDIR: str = "uploads/photos"
PHOTO_MIN_SIDE_PX: int = 100          # أصغر بُعد مقبول (يستبعد الأيقونات الصغيرة)
PHOTO_MAX_ASPECT_RATIO: float = 1.6   # أقصى نسبة بين الطول والعرض (يستبعد الشعارات والشرائط العريضة)
PHOTO_SEARCH_MAX_PAGES: int = 2       # نبحث عن الصورة في أول صفحتين فقط
PHOTO_MAX_SIDE_PX: int = 600          # تصغير الصورة المحفوظة لتوفير المساحة

CANDIDATE_STATUSES: list[str] = ["New", "Screened", "Interview", "Offered", "Rejected"]