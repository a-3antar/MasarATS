"""تعريف مجرّد (Abstract) لأي محلّل مستند - كل صيغة ملف تنفّذ نفس الواجهة."""

from abc import ABC, abstractmethod


class DocumentParser(ABC):
    """واجهة موحّدة لاستخلاص النص من أي نوع ملف سيرة ذاتية."""

    @abstractmethod
    def extract_text(self, file_path: str) -> str:
        """استخلاص النص الكامل من الملف. يرفع DocumentParsingError عند الفشل."""
        raise NotImplementedError
