"""
تكامل Gemini كمزوّد ذكاء اصطناعي.

المرحلة الحالية: بدون أي rate limiting أو caching (كما طُلب صراحة) -
كل نداء extract_structured يذهب مباشرة لـ Gemini. يمكن إضافة الحدين لاحقاً
دون تغيير أي كود يستدعي هذه الخدمة (تُستدعى دائماً عبر الواجهة AIProvider).
"""

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from ai.base import AIProvider
from config.settings import get_settings
from core.exceptions import AIServiceError
from core.logging import get_logger

logger = get_logger(__name__)


def _pydantic_to_gemini_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """
    يحوّل Pydantic model إلى مخطط يقبله google-generativeai.

    مكتبة Gemini لا تدعم حقولاً يولّدها Pydantic مثل: default, title, $ref, $defs, anyOf.
    لذلك نفكّ الـ $ref، ونحوّل anyOf [X, null] إلى X مع nullable=True،
    ونحذف كل الحقول غير المدعومة، ونكتب الأنواع بأحرف كبيرة (STRING, OBJECT...).
    """
    json_schema = schema.model_json_schema()
    definitions: dict[str, Any] = json_schema.get("$defs", {})

    def convert(node: dict[str, Any]) -> dict[str, Any]:
        if "$ref" in node:
            return convert(definitions[node["$ref"].split("/")[-1]])

        if "anyOf" in node:
            options = node["anyOf"]
            non_null = [o for o in options if o.get("type") != "null"]
            result = convert(non_null[0]) if non_null else {"type": "STRING"}
            if len(non_null) < len(options):
                result["nullable"] = True
            return result

        node_type = str(node.get("type", "string")).upper()
        result: dict[str, Any] = {"type": node_type}

        if node_type == "OBJECT":
            result["properties"] = {
                name: convert(prop) for name, prop in node.get("properties", {}).items()
            }
            if node.get("required"):
                result["required"] = node["required"]
        elif node_type == "ARRAY":
            result["items"] = convert(node.get("items", {"type": "string"}))

        if "enum" in node:
            result["enum"] = node["enum"]

        return result

    return convert(json_schema)


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

        raw_text = ""
        try:
            # نبني الموديل هنا (وليس في __init__) لأن response_schema يعتمد على الـ schema
            # الممرَّر لكل استدعاء. التحويل داخل try حتى لا يخرج أي خطأ خام للواجهة.
            model = self._genai.GenerativeModel(
                model_name=self._settings.ai_model,
                generation_config={
                    "temperature": self._settings.ai_temperature,
                    "response_mime_type": "application/json",
                    "response_schema": _pydantic_to_gemini_schema(schema),
                    # الحد الافتراضي قد يقطع الاستجابة في سير ذاتية طويلة
                    "max_output_tokens": 8192,
                },
            )

            prompt = CV_EXTRACTION_PROMPT_TEMPLATE.format(cv_text=text[:15000])  # حد أمان لطول النص

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

    def translate_json(self, data: dict[str, Any], target_language: str = "Arabic") -> dict[str, Any]:
        """يترجم قيم dict إلى اللغة المطلوبة مع الحفاظ على البنية. يرفع AIServiceError عند الفشل."""
        from ai.prompts import TRANSLATION_PROMPT_TEMPLATE

        raw_text = ""
        try:
            model = self._genai.GenerativeModel(
                model_name=self._settings.ai_model,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                    "max_output_tokens": 8192,
                },
            )
            prompt = TRANSLATION_PROMPT_TEMPLATE.format(
                language=target_language,
                payload=json.dumps(data, ensure_ascii=False),
            )
            response = model.generate_content(prompt)
            raw_text = response.text
            result = json.loads(raw_text)
            if not isinstance(result, dict):
                raise ValueError("الاستجابة ليست كائن JSON.")
            return result
        except Exception as exc:
            logger.error("Gemini translation failed: %s | raw_response=%s", exc, raw_text[:2000])
            raise AIServiceError(f"فشل ترجمة البيانات: {exc}") from exc