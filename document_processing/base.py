"""تعريف مجرّد (Abstract) لأي محلّل مستند - كل صيغة ملف تنفّذ نفس الواجهة."""

from abc import ABC, abstractmethod
from collections.abc import Iterable

from core.constants import PHOTO_MAX_ASPECT_RATIO, PHOTO_MIN_SIDE_PX

# (بيانات الصورة، الامتداد، العرض، الارتفاع)
PhotoCandidate = tuple[bytes, str, int, int]


def _looks_like_photo(width: int, height: int) -> bool:
    """صورة شخصية محتملة: ليست صغيرة جداً ولا شريطاً عريضاً/طويلاً (شعار، خط فاصل...)."""
    if min(width, height) < PHOTO_MIN_SIDE_PX:
        return False
    return max(width, height) / min(width, height) <= PHOTO_MAX_ASPECT_RATIO


def pick_best_photo(images: Iterable[PhotoCandidate]) -> tuple[bytes, str] | None:
    """يختار أكبر صورة تبدو شخصية من الصور المستخرجة، أو None إن لم توجد."""
    best: tuple[bytes, str] | None = None
    best_area = 0
    for data, extension, width, height in images:
        if not _looks_like_photo(width, height):
            continue
        if width * height > best_area:
            best_area = width * height
            best = (data, extension)
    return best


class DocumentParser(ABC):
    """واجهة موحّدة لاستخلاص النص (والصورة) من أي نوع ملف سيرة ذاتية."""

    @abstractmethod
    def extract_text(self, file_path: str) -> str:
        """استخلاص النص الكامل من الملف. يرفع DocumentParsingError عند الفشل."""
        raise NotImplementedError

    def extract_photo(self, file_path: str) -> tuple[bytes, str] | None:
        """استخراج صورة المرشح (بيانات، امتداد) إن وُجدت. الافتراضي: لا توجد صورة."""
        return None