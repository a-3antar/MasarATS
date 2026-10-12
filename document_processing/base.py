
import io
from abc import ABC, abstractmethod
from collections.abc import Iterable

from core.constants import (
    FACE_CROP_PADDING,
    FACE_MIN_SIZE_PX,
    PHOTO_MAX_ASPECT_RATIO,
    PHOTO_MIN_SIDE_PX,
)

PhotoCandidate = tuple[bytes, str, int, int]


def _looks_like_photo(width: int, height: int) -> bool:
    if min(width, height) < PHOTO_MIN_SIDE_PX:
        return False
    return max(width, height) / min(width, height) <= PHOTO_MAX_ASPECT_RATIO


def pick_best_photo(
    images: Iterable[PhotoCandidate],
    page_area: float | None = None,
    max_coverage: float = 1.0,
) -> tuple[bytes, str] | None:
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
    from ai.vision import detect_face_box

    ratios = detect_face_box(image_bytes)
    if ratios is None:
        return None
    xmin, ymin, xmax, ymax = ratios
    return int(xmin * width), int(ymin * height), int((xmax - xmin) * width), int((ymax - ymin) * height)


def _face_box_from_haar(rgb) -> tuple[int, int, int, int] | None:
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

    @abstractmethod
    def extract_text(self, file_path: str) -> str:
        raise NotImplementedError

    def extract_photo(self, file_path: str) -> tuple[bytes, str] | None:
        return None

    def is_scanned(self, file_path: str) -> bool:
        return False

    def render_first_page_png(self, file_path: str) -> bytes | None:
        return None
