"""حساب إجمالي سنوات الخبرة من تواريخ الوظائف (بدل الاعتماد على رقم مكتوب في السيرة)."""

import re
from datetime import date

from ai.schemas import ExperienceItem

_PRESENT_WORDS = (
    "present", "current", "now", "ongoing", "to date", "till date",
    "حتى الآن", "حتى الان", "إلى الآن", "الى الان", "حالياً", "حاليا", "الآن", "الان",
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def _month_index(today: date) -> int:
    return today.year * 12 + today.month - 1


def _to_month_index(value: str | None, is_end: bool, today: date) -> int | None:
    """يحوّل تاريخاً نصياً (05/2025 أو May 2025 أو 2025 أو Present) إلى رقم شهر تسلسلي."""
    if not value:
        return None
    text = value.strip().lower()
    if any(word in text for word in _PRESENT_WORDS):
        return _month_index(today)

    year_match = _YEAR_RE.search(text)
    if not year_match:
        return None
    year = int(year_match.group(0))
    rest = text.replace(year_match.group(0), " ")

    month = None
    number = re.search(r"\d{1,2}", rest)
    if number and 1 <= int(number.group(0)) <= 12:
        month = int(number.group(0))
    else:
        for name, value_ in _MONTHS.items():
            if name in rest:
                month = value_
                break
    if month is None:
        month = 12 if is_end else 1  # سنة فقط: البداية يناير والنهاية ديسمبر
    return year * 12 + month - 1


def estimate_total_years(experience: list[ExperienceItem], today: date | None = None) -> float | None:
    """إجمالي سنوات الخبرة من كل الوظائف بدون احتساب الفترات المتداخلة مرتين. None إن تعذّر الحساب."""
    today = today or date.today()
    intervals: list[tuple[int, int]] = []
    for item in experience:
        start = _to_month_index(item.start_date, False, today)
        if start is None:
            continue
        end = _to_month_index(item.end_date, True, today)
        if end is None:
            end = _month_index(today)  # لا يوجد تاريخ نهاية: نعتبرها وظيفة حالية
        if end >= start:
            intervals.append((start, end))

    if not intervals:
        return None

    intervals.sort()
    total_months = 0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total_months += current_end - current_start
            current_start, current_end = start, end
    total_months += current_end - current_start

    return round(total_months / 12, 1)