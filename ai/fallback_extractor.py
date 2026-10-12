
import re

from ai.schemas import CandidateProfile

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(\+?\d[\d \-()]{7,}\d)")


def extract_basic_profile(raw_text: str, fallback_name: str) -> CandidateProfile:
    email_match = _EMAIL_RE.search(raw_text)
    phone_match = _PHONE_RE.search(raw_text)

    return CandidateProfile(
        full_name=fallback_name,
        email=email_match.group(0) if email_match else None,
        phone=phone_match.group(0).strip() if phone_match else None,
        summary="تم الاستخراج بدون ذكاء اصطناعي (لا يوجد GEMINI_API_KEY) - يُنصح بمراجعة البيانات يدوياً.",
    )
