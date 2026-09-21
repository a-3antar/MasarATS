"""
كشف المرشحين المكررين.
تطابق قوي (يمنع الحفظ): البريد الإلكتروني، الهاتف، رابط LinkedIn.
تطابق ضعيف (تنبيه فقط): تشابه الاسم.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from core.constants import (
    DUPLICATE_NAME_SIMILARITY_THRESHOLD,
    DUPLICATE_SCAN_LIMIT,
    PHONE_MATCH_DIGITS,
    PHONE_MIN_DIGITS,
)
from models.candidate import Candidate
from repositories.candidate_repository import CandidateRepository

_LINKEDIN_RE = re.compile(r"linkedin\.com/(?:in|pub)/([^/?#\s]+)", re.IGNORECASE)
_TATWEEL_RE = re.compile("\u0640")
_ARABIC_LETTER_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})


def normalize_email(value: str | None) -> str | None:
    email = (value or "").strip().lower()
    return email or None


def normalize_phone(value: str | None) -> str | None:
    """يحوّل الرقم لأرقام إنجليزية فقط ويقارن بآخر 10 خانات (يتجاهل +20 و 0020 و 0 البادئة)."""
    digits = "".join(
        str(unicodedata.digit(ch)) for ch in (value or "") if ch.isdigit()
    )
    if len(digits) < PHONE_MIN_DIGITS:
        return None
    return digits[-PHONE_MATCH_DIGITS:]


def normalize_linkedin(value: str | None) -> str | None:
    """يستخرج معرّف الحساب (slug) من رابط LinkedIn بغض النظر عن www أو https أو الشرطة الأخيرة."""
    match = _LINKEDIN_RE.search(value or "")
    return match.group(1).lower() if match else None


def normalize_name(value: str | None) -> str | None:
    """اسم مطبّع: حروف صغيرة، بدون تشكيل/تطويل، توحيد الألف والتاء المربوطة، وكلمات مرتبة أبجدياً."""
    text = unicodedata.normalize("NFKD", (value or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _TATWEEL_RE.sub("", text).translate(_ARABIC_LETTER_MAP)
    tokens = re.findall(r"[^\W\d_]+", text)
    if len(tokens) < 2:  # اسم من كلمة واحدة لا يصلح للمقارنة (كثير من الأشخاص باسم "Ahmed")
        return None
    return " ".join(sorted(tokens))


@dataclass
class DuplicateMatch:
    candidate: Candidate
    reasons: list[str] = field(default_factory=list)
    is_strong: bool = False

    def describe(self) -> str:
        code = self.candidate.candidate_code or "-"
        return f"{self.candidate.full_name} ({code}) — تطابق: {'، '.join(self.reasons)}"


class DuplicateDetector:
    def __init__(self, candidates: CandidateRepository) -> None:
        self._candidates = candidates

    def find_duplicates(
        self,
        *,
        full_name: str | None,
        email: str | None,
        phone: str | None,
        linkedin_url: str | None,
        exclude_id: int | None = None,
    ) -> list[DuplicateMatch]:
        """يرجع كل المرشحين المحتمل تكرارهم، القوي منهم أولاً."""
        email_key = normalize_email(email)
        phone_key = normalize_phone(phone)
        linkedin_key = normalize_linkedin(linkedin_url)
        name_key = normalize_name(full_name)

        matches: list[DuplicateMatch] = []
        for existing in self._candidates.list_all(limit=DUPLICATE_SCAN_LIMIT):
            if exclude_id is not None and existing.id == exclude_id:
                continue

            match = DuplicateMatch(candidate=existing)

            if email_key and email_key == normalize_email(existing.email):
                match.reasons.append("البريد الإلكتروني")
            if phone_key and phone_key == normalize_phone(existing.phone):
                match.reasons.append("رقم الهاتف")
            if linkedin_key and linkedin_key == normalize_linkedin(existing.linkedin_url):
                match.reasons.append("رابط LinkedIn")
            match.is_strong = bool(match.reasons)

            existing_name = normalize_name(existing.full_name)
            if name_key and existing_name:
                similarity = SequenceMatcher(None, name_key, existing_name).ratio()
                if similarity >= DUPLICATE_NAME_SIMILARITY_THRESHOLD:
                    match.reasons.append(f"تشابه الاسم ({similarity:.0%})")

            if match.reasons:
                matches.append(match)

        matches.sort(key=lambda m: not m.is_strong)
        return matches