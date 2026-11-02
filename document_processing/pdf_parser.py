import re

from ai.vision import transcribe_image
from core.constants import (
    OCR_DPI,
    SCANNED_AVG_CHARS_PER_PAGE,
    OCR_MAX_views,
    OCR_MIN_CHARS_PER_PAGE,
    PHOTO_MAX_PAGE_COVERAGE,
    PHOTO_SEARCH_MAX_views,
)
from core.exceptions import AIServiceError, DocumentParsingError
from core.logging import get_logger
from document_processing.base import DocumentParser, PhotoCandidate,  pick_best_photo

logger = get_logger(__name__)

_READABLE_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF"
    r"A-Za-z0-9\s.,:;!?()\[\]{}\-_/\\@+#&%$*|'\"<>=•·–—،؛؟]"
)
_MIN_READABLE_RATIO = 0.7
_MIN_CHARS_TO_JUDGE = 40


def _is_garbled(text: str) -> bool:
    """نص PDF تالف: خط بلا خريطة Unicode يُخرج رموزاً عشوائية بدل الحروف."""
    compact = "".join(text.split())
    if len(compact) < _MIN_CHARS_TO_JUDGE:
        return False
    readable = sum(1 for ch in compact if _READABLE_RE.match(ch))
    return readable / len(compact) < _MIN_READABLE_RATIO


class PDFParser(DocumentParser):

    def extract_text(self, file_path: str) -> str:
        try:
            import pymupdf as fitz
        except ImportError as exc:
            raise DocumentParsingError("مكتبة PyMuPDF غير مثبّتة (pip install pymupdf).") from exc

        try:
            text_parts: list[str] = []
            vision_views = 0
            last_error: DocumentParsingError | None = None
            with fitz.open(file_path) as document:
                for page in document:
                    page_text = page.get_text().strip()
                    garbled = _is_garbled(page_text)
                    if (len(page_text) < OCR_MIN_CHARS_PER_PAGE or garbled) and vision_views < OCR_MAX_views:
                        vision_views += 1
                        try:
                            vision_text = self._read_page_with_vision(page)
                        except DocumentParsingError as exc:
                            last_error = exc
                            logger.warning("Vision failed for page %s: %s", page.number + 1, exc)
                            vision_text = ""
                        if vision_text:
                            page_text = vision_text if garbled else f"{page_text}\n{vision_text}".strip()
                        elif garbled:
                            page_text = ""
                    elif garbled:
                        page_text = ""
                    text_parts.append(page_text)

            text = "\n".join(p for p in text_parts if p).strip()
            if vision_views:
                logger.info("Gemini Vision used for %s page(s) of %s", vision_views, file_path)

            if not text:
                if last_error is not None:
                    raise last_error
                raise DocumentParsingError("لم يتم العثور على نص في الملف حتى بعد قراءته بالذكاء الاصطناعي.")
            return text
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"فشل تحليل ملف PDF: {exc}") from exc

    @staticmethod
    def _read_page_with_vision(page) -> str:
        page_number = page.number + 1
        try:
            pixmap = page.get_pixmap(dpi=OCR_DPI)
            return transcribe_image(pixmap.tobytes("png"), "image/png")
        except AIServiceError as exc:
            raise DocumentParsingError(
                f"تعذّرت قراءة الصفحة {page_number} (صفحة صورية تحتاج OCR): {exc}"
            ) from exc
        
    def extract_photo(self, file_path: str) -> tuple[bytes, str] | None:
        try:
            import pymupdf as fitz
        except ImportError:
            return None

        try:
            found: list[PhotoCandidate] = []
            with fitz.open(file_path) as document:
                first_page = document[0]
                page_area = first_page.rect.width * first_page.rect.height

                for page_index in range(min(len(document), PHOTO_SEARCH_MAX_views)):
                    for image_info in document[page_index].get_images(full=True):
                        extracted = document.extract_image(image_info[0])
                        if extracted:
                            found.append((
                                extracted["image"],
                                extracted.get("ext", "png"),
                                extracted["width"],
                                extracted["height"],
                            ))

                standalone = pick_best_photo(
                    [(d, e, w, h) for d, e, w, h in found if not self._is_page_sized(w, h, first_page)]
                )
                if standalone:
                    return standalone


        except Exception as exc:
            logger.warning("Photo extraction from PDF failed: %s", exc)
            return None

    @staticmethod
    def _is_page_sized(width: int, height: int, page) -> bool:
        page_ratio = page.rect.width / page.rect.height
        image_ratio = width / height
        similar_shape = abs(page_ratio - image_ratio) / page_ratio < 0.1
        large = width >= page.rect.width * PHOTO_MAX_PAGE_COVERAGE and height >= page.rect.height * PHOTO_MAX_PAGE_COVERAGE
        return similar_shape and large

    def is_scanned(self, file_path: str) -> bool:
        try:
            import pymupdf as fitz
            with fitz.open(file_path) as document:
                if not len(document):
                    return False
                texts = [page.get_text().strip() for page in document]

            non_empty = [t for t in texts if t]
            if not non_empty:
                return True
            if _is_garbled("\n".join(non_empty)):
                return True
            return sum(len(t) for t in non_empty) / len(non_empty) < SCANNED_AVG_CHARS_PER_PAGE
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scanned check failed: %s", exc)
            return False

    def render_first_page_png(self, file_path: str) -> bytes | None:
        try:
            import pymupdf as fitz
            with fitz.open(file_path) as document:
                return document[0].get_pixmap(dpi=200).tobytes("png")
        except Exception as exc:  # noqa: BLE001
            logger.warning("First page render failed: %s", exc)
            return None

