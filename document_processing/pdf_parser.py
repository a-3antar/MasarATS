"""استخلاص النص من ملفات PDF باستخدام PyMuPDF (fitz)."""

from core.exceptions import DocumentParsingError
from document_processing.base import DocumentParser


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
