"""
تكامل Gemini كمزوّد ذكاء اصطناعي.

المرحلة الحالية: بدون أي rate limiting أو caching (كما طُلب صراحة) -
كل نداء extract_structured يذهب مباشرة لـ Gemini. يمكن إضافة الحدين لاحقاً
دون تغيير أي كود يستدعي هذه الخدمة (تُستدعى دائماً عبر الواجهة AIProvider).
"""

import json

from pydantic import BaseModel, ValidationError

from ai.base import AIProvider
from config.settings import get_settings
from core.exceptions import AIServiceError
from core.logging import get_logger

logger = get_logger(__name__)


class GeminiService(AIProvider):
    """مزوّد الذكاء الاصطناعي المعتمد على Google Gemini."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise AIServiceError("لم يتم ضبط GEMINI_API_KEY في ملف .env")

        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise AIServiceError("مكتبة google-generativeai غير مثبّتة.") from exc

        self._genai = genai
        genai.configure(api_key=settings.gemini_api_key)
        self._settings = settings

    def extract_structured(self, text: str, schema: type[BaseModel]) -> BaseModel:
        from ai.prompts import CV_EXTRACTION_PROMPT_TEMPLATE

        # نبني الموديل هنا (وليس في __init__) لأن response_schema يعتمد على الـ schema
        # الممرَّر لكل استدعاء - يسمح باستخدام GeminiService لأكثر من نوع مخطط لاحقاً.
        model = self._genai.GenerativeModel(
            model_name=self._settings.ai_model,
            generation_config={
                "temperature": self._settings.ai_temperature,
                "response_mime_type": "application/json",
                # هذا هو الإصلاح الأساسي: إلزام Gemini فعلياً بالمخطط بدل الاعتماد فقط
                # على وصفه نصياً في الـ prompt، وهو ما كان يسبب إرجاع حقول null
                # (مثل full_name وemail) رغم وجودها بوضوح في النص.
                "response_schema": schema,
                # الحد الافتراضي قد يقطع الاستجابة في سير ذاتية طويلة (30+ سنة خبرة مثلاً)
                "max_output_tokens": 8192,
            },
        )

        prompt = CV_EXTRACTION_PROMPT_TEMPLATE.format(cv_text=text[:15000])  # حد أمان بسيط لطول النص

        raw_text = ""
        try:
            response = model.generate_content(prompt)
            raw_text = response.text
            raw_json = json.loads(raw_text)
            return schema.model_validate(raw_json)
        except ValidationError as exc:
            logger.error(
                "Gemini returned data that failed schema validation: %s | raw_response=%s",
                exc, raw_text[:2000],
            )
            raise AIServiceError("استجابة الذكاء الاصطناعي لم تطابق الشكل المتوقع.") from exc
        except Exception as exc:
            logger.error("Gemini call failed: %s | raw_response=%s", exc, raw_text[:2000])
            raise AIServiceError(f"فشل استدعاء Gemini: {exc}") from exc
