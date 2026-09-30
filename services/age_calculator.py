"""حساب العمر من تاريخ ميلاد نصي (بدل الاعتماد على حساب النموذج)."""

import re
from datetime import date

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_MIN_AGE, _MAX_AGE = 15, 80


def _parse_birth(value: str) -> tuple[int, int | None, int | None] | None:
    """يرجع (سنة، شهر أو None، يوم أو None)."""
    text = (value or "").strip().lower()
    year_match = _YEAR_RE.search(text)
    if not year_match:
        return None
    year = int(year_match.group(0))
    rest = text.replace(year_match.group(0), " ")

    month = next((n for name, n in _MONTHS.items() if name in rest), None)
    day = None
    numbers = [int(n) for n in re.findall(r"\d{1,2}", rest)]
    if month is None and numbers:
        # صيغة 15/03/1987 أو 03/1987
        if len(numbers) >= 2 and 1 <= numbers[1] <= 12:
            day, month = numbers[0], numbers[1]
        elif 1 <= numbers[0] <= 12:
            month = numbers[0]
    elif numbers and 1 <= numbers[0] <= 31:
        day = numbers[0]
    return year, month, day


def calculate_age(birth_date: str | None, today: date | None = None) -> int | None:
    """العمر بالسنوات الكاملة. إن غاب الشهر نفترض منتصف السنة، وإن غاب اليوم نفترض اليوم 1."""
    parsed = _parse_birth(birth_date or "")
    if parsed is None:
        return None
    today = today or date.today()
    year, month, day = parsed
    age = today.year - year
    if month is not None:
        if (today.month, today.day) < (month, day or 1):
            age -= 1
    else:
        age -= 1  # بدون شهر: تقدير متحفظ
    return age if _MIN_AGE <= age <= _MAX_AGE else None