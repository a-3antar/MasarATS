"""توحيد أسماء المهارات للمقارنة: 'Microsoft Excel' = 'MS Excel' = 'excel'، 'PowerBI' = 'Power BI'."""

import re
from collections.abc import Iterable
from difflib import SequenceMatcher

from core.constants import SKILL_FUZZY_MIN_LENGTH, SKILL_FUZZY_THRESHOLD

_VENDOR_PREFIXES = ("microsoft ", "ms ", "adobe ", "autodesk ", "google ", "oracle ", "siemens ")
_NOISE_SUFFIXES = (" software", " skills", " skill", " knowledge", " program", " application")
# أضف هنا أي اختصارات شائعة في مجالك (المفتاح والقيمة بعد التنظيف الأولي)
_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "ppt": "powerpoint",
    "ms office": "office",
    "msoffice": "office",
}
_CLEAN_RE = re.compile(r"[^\w\s+#.]")


def canonical_skill(skill: str) -> str:
    """الصيغة القياسية للمهارة (بدون مسافات أو شرطات أو اسم الشركة المصنّعة)."""
    text = _CLEAN_RE.sub(" ", (skill or "").lower().replace("&", " and "))
    text = re.sub(r"\s+", " ", text).strip()

    for prefix in _VENDOR_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    for suffix in _NOISE_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break

    text = _ALIASES.get(text, text)
    return re.sub(r"[\s.\-_]", "", text)


def canonical_skill_set(skills: Iterable[str]) -> set[str]:
    return {key for key in (canonical_skill(s) for s in skills) if key}


def has_skill(required_skill: str, candidate_keys: set[str]) -> bool:
    """هل المهارة المطلوبة موجودة لدى المرشح؟ تطابق قياسي، ثم تشابه إملائي عالٍ (أخطاء كتابة)."""
    key = canonical_skill(required_skill)
    if not key:
        return False
    if key in candidate_keys:
        return True
    if len(key) < SKILL_FUZZY_MIN_LENGTH:
        return False
    return any(
        len(other) >= SKILL_FUZZY_MIN_LENGTH
        and SequenceMatcher(None, key, other).ratio() >= SKILL_FUZZY_THRESHOLD
        for other in candidate_keys
    )