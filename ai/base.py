"""واجهة مجردة لأي مزوّد ذكاء اصطناعي - تسمح باستبدال Gemini بمزوّد آخر مستقبلاً دون تغيير الخدمات."""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class AIProvider(ABC):
    """واجهة موحّدة لاستخلاص بيانات مهيكلة (Structured Output) من نص حر."""

    @abstractmethod
    def extract_structured(self, text: str, schema: type[BaseModel]) -> BaseModel:
        """يرسل النص للنموذج ويرجع كائناً مطابقاً للـ schema المُعطى. يرفع AIServiceError عند الفشل."""
        raise NotImplementedError
