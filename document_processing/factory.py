"""
Factory لاختيار محلّل المستند المناسب حسب امتداد الملف.
بقية التطبيق يستدعي فقط `DocumentParserFactory.get_parser(...)` ولا يعرف
أي شيء عن PyMuPDF أو python-docx تحديداً - يسهّل إضافة صيغ جديدة لاحقاً.
"""

from pathlib import Path

from core.exceptions import UnsupportedFileTypeError
from document_processing.base import DocumentParser
from document_processing.pdf_parser import PDFParser
from document_processing.text_parser import TextParser
from document_processing.word_parser import WordParser


class DocumentParserFactory:
    """يُرجع محلّل المستند المناسب بناءً على امتداد الملف."""

    _parsers: dict[str, type[DocumentParser]] = {
        ".pdf": PDFParser,
        ".docx": WordParser,
        ".txt": TextParser,
    }

    @classmethod
    def get_parser(cls, file_path: str) -> DocumentParser:
        extension = Path(file_path).suffix.lower()
        parser_class = cls._parsers.get(extension)
        if parser_class is None:
            raise UnsupportedFileTypeError(f"صيغة الملف غير مدعومة: {extension}")
        return parser_class()
