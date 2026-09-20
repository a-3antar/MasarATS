"""تعريف مجرّد (Abstract) لأي محلّل مستند - كل صيغة ملف تنفّذ نفس الواجهة."""

import io
from abc import ABC, abstractmethod
from collections.abc import Iterable

from core.constants import (
    FACE_CROP_PADDING,
    FACE_MIN_SIZE_PX,
    PHOTO_MAX_ASPECT_RATIO,
    PHOTO_MIN_SIDE_PX,
)

# (بيانات الصورة، الامتداد، العرض، الارتفاع)
PhotoCandidate = tuple[bytes, str, int, int]


def _looks_like_photo(width: int, height: int) -> bool:
    """صورة شخصية محتملة: ليست صغيرة جداً ولا شريطاً عريضاً/طويلاً (شعار، خط فاصل...)."""
    if min(width, height) < PHOTO_MIN_SIDE_PX:
        return False
    return max(width, height) / min(width, height) <= PHOTO_MAX_ASPECT_RATIO


def pick_best_photo(
    images: Iterable[PhotoCandidate],
    page_area: float | None = None,
    max_coverage: float = 1.0,
) -> tuple[bytes, str] | None:
    """
    يختار أكبر صورة تبدو شخصية، أو None إن لم توجد.
    إذا مُرِّرت page_area فالصور التي تغطي أكثر من max_coverage من مساحة الصفحة تُستبعد
    (لأنها غالباً صورة الصفحة كاملة وليست صورة شخصية).
    """
    best: tuple[bytes, str] | None = None
    best_area = 0
    for data, extension, width, height in images:
        if not _looks_like_photo(width, height):
            continue
        area = width * height
        if page_area and area / page_area > max_coverage:
            continue
        if area > best_area:
            best_area = area
            best = (data, extension)
    return best


def crop_face_from_image(image_bytes: bytes) -> tuple[bytes, str] | None:
    """
    يكتشف وجه صاحب السيرة في صورة (مثل صفحة سيرة ذاتية مصدّرة كصورة) ويقصّه مع هامش.
    الأولوية لـ Gemini (أدق مع الصور الصغيرة/الدائرية)، ثم OpenCV Haar كاحتياط.
    يرجع (بيانات PNG، "png") أو None إن لم يوجد وجه.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            rgb = source.convert("RGB")

        box = _face_box_from_gemini(image_bytes, rgb.width, rgb.height) or _face_box_from_haar(rgb)
        if box is None:
            return None

        x, y, w, h = box
        # قص مربع مركزه مركز الوجه، بضلع = أكبر بُعد للوجه + هامش
        side = int(max(w, h) * (1 + 2 * FACE_CROP_PADDING))
        center_x, center_y = x + w // 2, y + h // 2
        left = max(center_x - side // 2, 0)
        top = max(center_y - side // 2, 0)
        right = min(left + side, rgb.width)
        bottom = min(top + side, rgb.height)
        
        buffer = io.BytesIO()
        rgb.crop((left, top, right, bottom)).save(buffer, format="PNG")
        return buffer.getvalue(), "png"
    except Exception:  # noqa: BLE001 - فشل الاكتشاف لا يوقف رفع السيرة
        return None


def _face_box_from_gemini(image_bytes: bytes, width: int, height: int) -> tuple[int, int, int, int] | None:
    """صندوق الوجه (x, y, w, h) بالبكسل من Gemini، أو None."""
    from ai.vision import detect_face_box

    ratios = detect_face_box(image_bytes)
    if ratios is None:
        return None
    xmin, ymin, xmax, ymax = ratios
    return int(xmin * width), int(ymin * height), int((xmax - xmin) * width), int((ymax - ymin) * height)


def _face_box_from_haar(rgb) -> tuple[int, int, int, int] | None:
    """صندوق الوجه (x, y, w, h) بالبكسل من OpenCV Haar، أو None."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    gray = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.05, minNeighbors=3, minSize=(FACE_MIN_SIZE_PX // 2, FACE_MIN_SIZE_PX // 2)
    )
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return int(x), int(y), int(w), int(h)

class DocumentParser(ABC):
    """واجهة موحّدة لاستخلاص النص (والصورة) من أي نوع ملف سيرة ذاتية."""

    @abstractmethod
    def extract_text(self, file_path: str) -> str:
        """استخلاص النص الكامل من الملف. يرفع DocumentParsingError عند الفشل."""
        raise NotImplementedError

    def extract_photo(self, file_path: str) -> tuple[bytes, str] | None:
        """استخراج صورة المرشح (بيانات، امتداد) إن وُجدت. الافتراضي: لا توجد صورة."""
        return None