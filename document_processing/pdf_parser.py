"""استخلاص النص والصورة من ملفات PDF باستخدام PyMuPDF (fitz)، مع قراءة الصفحات الصورية عبر Gemini Vision."""

from ai.vision import transcribe_image
from core.constants import (
    OCR_DPI,
    OCR_MAX_views,
    OCR_MIN_CHARS_PER_PAGE,
    PHOTO_MAX_PAGE_COVERAGE,
    PHOTO_SEARCH_MAX_views,
)
from core.exceptions import AIServiceError, DocumentParsingError
from core.logging import get_logger
from document_processing.base import DocumentParser, PhotoCandidate, crop_face_from_image, pick_best_photo

logger = get_logger(__name__)


class PDFParser(DocumentParser):
    """يستخلص النص من ملفات PDF: مباشرة للصفحات النصية، وعبر Gemini Vision للصفحات الصورية."""

    def extract_text(self, file_path: str) -> str:
        try:
            import pymupdf as fitz  # الاسم الجديد للحزمة؛ "fitz" أصبح مهجوراً في PyMuPDF الحديثة
        except ImportError as exc:
            raise DocumentParsingError("مكتبة PyMuPDF غير مثبّتة (pip install pymupdf).") from exc

        try:
            text_parts: list[str] = []
            vision_views = 0
            with fitz.open(file_path) as document:
                for page in document:
                    page_text = page.get_text().strip()
                    if len(page_text) < OCR_MIN_CHARS_PER_PAGE and vision_views < OCR_MAX_views:
                        vision_text = self._read_page_with_vision(page)
                        vision_views += 1
                        if vision_text:
                            page_text = f"{page_text}\n{vision_text}".strip()
                    text_parts.append(page_text)

            text = "\n".join(text_parts).strip()
            if vision_views:
                logger.info("Gemini Vision used for %s page(s) of %s", vision_views, file_path)

            if not text:
                raise DocumentParsingError("لم يتم العثور على نص في الملف حتى بعد قراءته بالذكاء الاصطناعي.")
            return text
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"فشل تحليل ملف PDF: {exc}") from exc

    @staticmethod
    def _read_page_with_vision(page) -> str:
        """يحوّل الصفحة إلى صورة PNG ويرسلها لـ Gemini لنسخ نصها."""
        page_number = page.number + 1
        try:
            pixmap = page.get_pixmap(dpi=OCR_DPI)
            return transcribe_image(pixmap.tobytes("png"), "image/png")
        except AIServiceError as exc:
            raise DocumentParsingError(
                f"تعذّرت قراءة الصفحة {page_number} (صفحة صورية تحتاج OCR): {exc}"
            ) from exc
        
    def extract_photo(self, file_path: str) -> tuple[bytes, str] | None:
        """
        يبحث عن الصورة الشخصية في أول صفحات الـ PDF:
        1) صورة مستقلة لا تغطي معظم الصفحة.
        2) إن لم توجد (صفحة مصدّرة كصورة كاملة): نكتشف الوجه في صورة الصفحة ونقصّه.
        أي فشل لا يوقف رفع السيرة.
        """
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

                # مساحة الصفحة بالبكسل تقريباً عند 72 dpi؛ نقارنها بمساحة الصورة بنفس الوحدة عبر نسبة تقريبية
                standalone = pick_best_photo(
                    [(d, e, w, h) for d, e, w, h in found if not self._is_page_sized(w, h, first_page)]
                )
                if standalone:
                    return standalone

                # لا توجد صورة مستقلة: نقصّ الوجه من صورة الصفحة الأولى
                pixmap = first_page.get_pixmap(dpi=200)
                return crop_face_from_image(pixmap.tobytes("png"))
        except Exception as exc:
            logger.warning("Photo extraction from PDF failed: %s", exc)
            return None

    @staticmethod
    def _is_page_sized(width: int, height: int, page) -> bool:
        """هل الصورة تغطي معظم الصفحة؟ نقارن نسبة الأبعاد ومساحة الصورة بالنسبة لأبعاد الصفحة."""
        page_ratio = page.rect.width / page.rect.height
        image_ratio = width / height
        similar_shape = abs(page_ratio - image_ratio) / page_ratio < 0.1
        # الصور الشخصية عادة أصغر بكثير من الصفحة؛ الصورة ذات شكل الصفحة وبأبعاد كبيرة هي صفحة كاملة
        large = width >= page.rect.width * PHOTO_MAX_PAGE_COVERAGE and height >= page.rect.height * PHOTO_MAX_PAGE_COVERAGE
        return similar_shape and large