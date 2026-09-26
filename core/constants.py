"""ثوابت مشتركة عبر التطبيق - بدل نشر الأرقام والقيم الثابتة داخل الكود (no magic numbers)."""

ALLOWED_CV_EXTENSIONS: set[str] = {".pdf", ".docx", ".pptx", ".txt"}
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
PHOTO_SEARCH_MAX_views: int = 2       # نبحث عن الصورة في أول صفحتين فقط
PHOTO_MAX_SIDE_PX: int = 600          # تصغير الصورة المحفوظة لتوفير المساحة

CANDIDATE_STATUSES: list[str] = APPLICATION_STATUSES  # حالة المرشح تستخدم نفس مراحل خط التوظيف

# قراءة الصفحات الصورية عبر Gemini Vision
OCR_DPI: int = 150                  # كافٍ للقراءة ويقلل حجم الصورة المرسلة
OCR_MIN_CHARS_PER_PAGE: int = 30    # أقل من هذا العدد من الحروف → نعتبر الصفحة صورة
OCR_MAX_views: int = 5              # أقصى عدد صفحات تُرسل للقراءة لكل ملف (حماية من التكلفة)

# استبعاد الصور التي هي في الحقيقة صفحة كاملة، واكتشاف الوجه كبديل
PHOTO_MAX_PAGE_COVERAGE: float = 0.25  # صورة تغطي أكثر من هذه النسبة من مساحة الصفحة ليست صورة شخصية
FACE_CROP_PADDING: float = 0.6         # هامش حول الوجه المكتشف (نسبة من عرض الوجه) ليظهر الرأس والكتفان
FACE_MIN_SIZE_PX: int = 60             # أصغر وجه مقبول عند الاكتشاف

# كشف المرشحين المكررين
DUPLICATE_NAME_SIMILARITY_THRESHOLD: float = 0.88  # أقل نسبة تشابه اسم تُعتبر تطابقاً ضعيفاً
PHONE_MIN_DIGITS: int = 8                          # أقل من هذا لا يُعتبر رقماً صالحاً للمقارنة
PHONE_MATCH_DIGITS: int = 10                       # نقارن آخر 10 أرقام (يتجاوز كود الدولة)
DUPLICATE_SCAN_LIMIT: int = 100_000                # حد أمان لعدد المرشحين الممسوحين

# مطابقة المهارات والبحث الذكي
SKILL_FUZZY_THRESHOLD: float = 0.88   # أقل تشابه إملائي يُعتبر نفس المهارة
SKILL_FUZZY_MIN_LENGTH: int = 5       # المهارات الأقصر (SAP, C#) تُقارن بتطابق تام فقط
SEARCH_MAX_CANDIDATES: int = 5000     # حد أمان لعدد المرشحين الممسوحين في البحث الذكي

# إدارة المقابلات
INTERVIEW_TYPES: list[str] = ["HR", "Technical", "Management", "Behavioral", "Final"]
INTERVIEW_STATUSES: list[str] = ["Scheduled", "Completed", "Cancelled"]

# التحليل الخلفي بالذكاء الاصطناعي
AI_BACKGROUND_WORKERS: int = 2   # عدد التحليلات المتزامنة في الخلفية (حماية لحصة Gemini)

MAX_WORKERS = 6    # أقصى عدد عمليات متزامنة (مجموع كل الخلفيات: الصور + التحليل + غيرها)

SCANNED_AVG_CHARS_PER_PAGE: int = 200   # متوسط أحرف أقل من هذا → PDF ممسوح
AI_RETRY_MAX_ATTEMPTS: int = 4
AI_RETRY_BASE_SECONDS: float = 4.0      # الانتظار: 4 ثم 8 ثم 16 ثانية (+ jitter)
ANALYSIS_PENDING, ANALYSIS_DONE, ANALYSIS_FAILED = "pending", "done", "failed"
PHOTO_BACKGROUND_WORKERS: int = 2

# لوحة المعلومات والتقارير
DASHBOARD_TOP_SKILLS: int = 10        # عدد المهارات في رسم "الأكثر تكراراً"
NEW_CV_DAYS: int = 7                  # "سير جديدة" = آخر كم يوماً
QUALIFIED_SCORE_THRESHOLD: float = 60.0  # درجة المطابقة التي يُعتبر بعدها المرشح مؤهلاً
MIN_CANDIDATES_PER_JOB: int = 3       # أقل من هذا العدد = وظيفة تحتاج مرشحين

# المطابقة الهجينة (Hybrid): وزن التشابه الدلالي الافتراضي عندما لا تحدد الوظيفة وزناً خاصاً بها
SEMANTIC_DEFAULT_WEIGHT: float = 0.2
EMBEDDING_MODEL_NAME: str = "gemini-embedding-001"