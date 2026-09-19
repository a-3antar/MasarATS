"""قراءة ملفات .txt مباشرة."""

from core.exceptions import DocumentParsingError
from document_processing.base import DocumentParser


class TextParser(DocumentParser):
    """يقرأ ملفات نصية عادية (.txt)."""

    def extract_text(self, file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()
            if not text:
                raise DocumentParsingError("الملف النصي فارغ.")
            return text
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"فشل قراءة الملف النصي: {exc}") from exc
