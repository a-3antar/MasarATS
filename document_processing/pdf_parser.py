"""استخلاص النص والصورة من ملفات PDF باستخدام PyMuPDF (fitz)."""

from core.constants import PHOTO_SEARCH_MAX_PAGES
from core.exceptions import DocumentParsingError
from core.logging import get_logger
from document_processing.base import DocumentParser, PhotoCandidate, pick_best_photo

logger = get_logger(__name__)


class PDFParser(DocumentParser):
    """يستخلص النص من ملفات PDF (نصية - وليست صور ممسوحة ضوئياً في هذه المرحلة)."""

    def extract_text(self, file_path: str) -> str:
        try:
            import pymupdf as fitz  # الاسم الجديد للحزمة؛ "fitz" أصبح مهجوراً في PyMuPDF الحديثة
        except ImportError as exc:
            raise DocumentParsingError("مكتبة PyMuPDF غير مثبّتة (pip install pymupdf).") from exc

        try:
            text_parts: list[str] = []
            with fitz.open(file_path) as document:
                for page in document:
                    text_parts.append(page.get_text())
            text = "\n".join(text_parts).strip()

            if not text:
                raise DocumentParsingError(
                    "لم يتم العثور على نص في الملف - قد يكون PDF ممسوحاً ضوئياً (يحتاج OCR غير مفعّل بعد)."
                )
            return text
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"فشل تحليل ملف PDF: {exc}") from exc

    def extract_photo(self, file_path: str) -> tuple[bytes, str] | None:
        """يبحث عن أنسب صورة شخصية في أول صفحات الـ PDF. أي فشل لا يوقف رفع السيرة."""
        try:
            import pymupdf as fitz
        except ImportError:
            return None

        try:
            found: list[PhotoCandidate] = []
            with fitz.open(file_path) as document:
                for page_index in range(min(len(document), PHOTO_SEARCH_MAX_PAGES)):
                    for image_info in document[page_index].get_images(full=True):
                        extracted = document.extract_image(image_info[0])
                        if extracted:
                            found.append((
                                extracted["image"],
                                extracted.get("ext", "png"),
                                extracted["width"],
                                extracted["height"],
                            ))
            return pick_best_photo(found)
        except Exception as exc:
            logger.warning("Photo extraction from PDF failed: %s", exc)
            return None