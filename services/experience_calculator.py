"""حساب إجمالي سنوات الخبرة من تواريخ الوظائف (بدل الاعتماد على رقم مكتوب في السيرة)."""

import re
from datetime import date

from ai.schemas import ExperienceItem

_PRESENT_WORDS = (
    "present", "current", "now", "ongoing", "to date", "till date", "till now",
    "حتى الآن", "حتى الان", "إلى الآن", "الى الان", "حالياً", "حاليا", "الآن", "الان",
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_DMY_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*((?:19|20)\d{2})")
_MY_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[/.\-]\s*((?:19|20)\d{2})")
_UNPARSABLE_KEY = (-1, -1)  # وظيفة بلا أي تاريخ مفهوم: تُوضع في آخر القائمة


def _month_index(today: date) -> int:
    return today.year * 12 + today.month - 1


def _to_month_index(value: str | None, is_end: bool, today: date) -> int | None:
    """يحوّل تاريخاً (14/2/2012 يوم/شهر/سنة، 05/2025، May 2025، 2025، Present) إلى رقم شهر تسلسلي."""
    if not value:
        return None
    text = value.strip().lower()
    if any(word in text for word in _PRESENT_WORDS):
        return _month_index(today)

    year = month = None
    if match := _DMY_RE.search(text):
        first, second, year = int(match[1]), int(match[2]), int(match[3])
        month = second if 1 <= second <= 12 else (first if 1 <= first <= 12 else None)
    elif match := _MY_RE.search(text):
        year = int(match[2])
        month = int(match[1]) if 1 <= int(match[1]) <= 12 else None
    elif year_match := _YEAR_RE.search(text):
        year = int(year_match.group(0))
        rest = text.replace(year_match.group(0), " ")
        month = next((n for name, n in _MONTHS.items() if name in rest), None)

    if year is None:
        return None
    if month is None:
        month = 12 if is_end else 1  # سنة فقط: البداية يناير والنهاية ديسمبر
    return year * 12 + month - 1


def _bounds(item: ExperienceItem, today: date) -> tuple[int | None, int | None]:
    """(بداية، نهاية) كأرقام أشهر. النهاية الفارغة تعني وظيفة حالية إن وُجدت بداية."""
    start = _to_month_index(item.start_date, False, today)
    end = _to_month_index(item.end_date, True, today)
    if end is None and start is not None:
        end = _month_index(today)
    return start, end


def sort_experience_newest_first(
    experience: list[ExperienceItem], today: date | None = None
) -> list[ExperienceItem]:
    """يرتّب الوظائف من الأحدث إلى الأقدم (حسب تاريخ النهاية ثم البداية). الوظائف بلا تواريخ تذهب للآخر."""
    today = today or date.today()

    def key(item: ExperienceItem) -> tuple[int, int]:
        start, end = _bounds(item, today)
        if start is None and end is None:
            return _UNPARSABLE_KEY
        end = end if end is not None else start
        return end, start if start is not None else end

    return sorted(experience, key=key, reverse=True)


def estimate_total_years(experience: list[ExperienceItem], today: date | None = None) -> float | None:
    """
    إجمالي سنوات الخبرة بدون احتساب الفترات المتداخلة مرتين. None إن تعذّر الحساب.
    وظيفة بلا تاريخ بداية (خطأ مطبعي مثل 2102) تبدأ من نهاية الوظيفة الأقدم منها مباشرة.
    """
    today = today or date.today()
    ordered = sort_experience_newest_first(experience, today)  # الأحدث أولاً
    bounds = [_bounds(item, today) for item in ordered]

    intervals: list[tuple[int, int]] = []
    for index, (start, end) in enumerate(bounds):
        if end is None:
            continue
        if start is None:
            # نهاية أقرب وظيفة أقدم (التالية في القائمة) لها نهاية مفهومة
            start = next((older_end for _, older_end in bounds[index + 1:] if older_end is not None), None)
            if start is None:
                continue
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