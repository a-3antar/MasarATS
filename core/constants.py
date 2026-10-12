
ALLOWED_CV_EXTENSIONS: set[str] = {".pdf", ".docx", ".pptx", ".txt"}
MAX_CV_FILE_SIZE_MB: int = 10

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

PHOTOS_SUBDIR: str = "uploads/photos"
PHOTO_MIN_SIDE_PX: int = 100
PHOTO_MAX_ASPECT_RATIO: float = 1.6
PHOTO_SEARCH_MAX_views: int = 2
PHOTO_MAX_SIDE_PX: int = 600

CANDIDATE_STATUSES: list[str] = APPLICATION_STATUSES

OCR_DPI: int = 150
OCR_MIN_CHARS_PER_PAGE: int = 30
OCR_MAX_views: int = 5

PHOTO_MAX_PAGE_COVERAGE: float = 0.25
FACE_CROP_PADDING: float = 0.6
FACE_MIN_SIZE_PX: int = 60

DUPLICATE_NAME_SIMILARITY_THRESHOLD: float = 0.88
PHONE_MIN_DIGITS: int = 8
PHONE_MATCH_DIGITS: int = 10
DUPLICATE_SCAN_LIMIT: int = 100_000

SKILL_FUZZY_THRESHOLD: float = 0.88
SKILL_FUZZY_MIN_LENGTH: int = 5
SEARCH_MAX_CANDIDATES: int = 5000

INTERVIEW_TYPES: list[str] = ["HR", "Technical", "Management", "Behavioral", "Final"]
INTERVIEW_STATUSES: list[str] = ["Scheduled", "Completed", "Cancelled"]

AI_BACKGROUND_WORKERS: int = 2

MAX_WORKERS = 6

SCANNED_AVG_CHARS_PER_PAGE: int = 200
AI_RETRY_MAX_ATTEMPTS: int = 4
AI_RETRY_BASE_SECONDS: float = 4.0
ANALYSIS_PENDING, ANALYSIS_DONE, ANALYSIS_FAILED = "pending", "done", "failed"
PHOTO_BACKGROUND_WORKERS: int = 2

DASHBOARD_TOP_SKILLS: int = 10
NEW_CV_DAYS: int = 7
QUALIFIED_SCORE_THRESHOLD: float = 60.0
MIN_CANDIDATES_PER_JOB: int = 3

SEMANTIC_DEFAULT_WEIGHT: float = 0.2
EMBEDDING_MODEL_NAME: str = "gemini-embedding-001"

INTERVIEW_STATUSES: list[str] = ["Scheduled", "In Progress", "Completed", "Cancelled"]
INTERVIEW_DECISIONS: list[str] = ["Continue", "Additional", "Hold", "Not Selected"]
QUESTION_TYPES: list[str] = ["text", "choice", "rating"]
QUESTION_DIFFICULTIES: list[str] = ["Low", "Medium", "High"]

EMPLOYMENT_TYPES: list[str] = ["Full-time", "Part-time", "Contract", "Internship", "Temporary"]
CAREER_LEVELS: list[str] = ["Intern", "Junior", "Mid-Level", "Senior", "Manager", "Director", "Executive"]
DEFAULT_SALARY_CURRENCY: str = "EGP"
DEFAULT_VACANCIES: int = 1
MATCH_HIGH_THRESHOLD: float = 80.0
MATCH_MEDIUM_THRESHOLD: float = 50.0
SKILL_STRONG_COVERAGE: float = 0.5
SKILL_GAP_COVERAGE: float = 0.25
JOB_TREND_WEEKS: int = 8
JOB_NEW_DAYS: int = 30
JOB_INSIGHT_MAX_SKILLS: int = 6

OFFER_STATUSES: list[str] = ["Draft", "Sent", "Accepted", "Declined", "Withdrawn"]
ACTIVE_OFFER_STATUSES: list[str] = ["Draft", "Sent", "Accepted"]
MIN_HIRES_FOR_TIME_STATS: int = 3
SECONDS_PER_DAY: int = 86_400

BULK_DELETE_LIMIT: int = 2
RECRUITER_MAX_UPLOAD_FILES: int = 5

SCORE_GOOD: float = 75.0
SCORE_MID: float = 50.0
