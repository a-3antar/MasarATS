"""
تكامل Gemini كمزوّد ذكاء اصطناعي، عبر مكتبة google-genai الجديدة.

كل نداء فعلي لـ Gemini يبني عميل (Client) مستقل خاص به باستخدام مفتاح قادم من
key_rotator.get_next_key() (تبديل دوري بين المفاتيح المتاحة) - لا توجد حالة
مشتركة (global state) بين الـ Threads كما كان الحال مع genai.configure() القديمة.

المرحلة الحالية: بدون أي rate limiting أو caching إضافي (كما طُلب صراحة).
"""

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from ai.base import AIProvider
from ai.key_rotator import get_next_key
from config.settings import get_settings
from core.exceptions import AIServiceError
from core.logging import get_logger

logger = get_logger(__name__)

_ATTACHED_FILE_NOTE = (
        "(السيرة الذاتية مرفقة كملف مع هذا الطلب. اقرأ نصها مباشرة بما في ذلك الصفحات الممسوحة، "
        "وإذا كان التصميم بعمودين فاقرأ كل عمود كاملاً، ثم استخرج البيانات.)"
    )

def _pydantic_to_gemini_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """
    يحوّل Pydantic model إلى مخطط يقبله google-genai (نفس بنية الحقول المدعومة
    في response_schema التي كانت تُستخدم مع google-generativeai: type, properties,
    items, required, enum, nullable - بأحرف كبيرة للأنواع STRING/OBJECT/ARRAY...).
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
    """مزوّد الذكاء الاصطناعي المعتمد على Google Gemini (عبر google-genai)."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key and not settings.alt_gemini_api_key:
            raise AIServiceError("لم يتم ضبط GEMINI_API_KEY في ملف .env")

        try:
            from google import genai
        except ImportError as exc:
            raise AIServiceError("مكتبة google-genai غير مثبّتة.") from exc

        self._genai = genai
        self._settings = settings

    def _client(self):
        """عميل مستقل لكل نداء - يستخدم المفتاح التالي في التبديل الدوري. آمن للتوازي."""
        return self._genai.Client(api_key=get_next_key())

   

    def extract_structured(self, text: str, schema: type[BaseModel]) -> BaseModel:
        from ai.prompts import CV_EXTRACTION_PROMPT_TEMPLATE

        prompt = CV_EXTRACTION_PROMPT_TEMPLATE.format(cv_text=text[:15000])
        return self._extract(prompt, schema)

    def extract_structured_from_file(self, data: bytes, mime_type: str, schema: type[BaseModel]) -> BaseModel:
        """نسخ + استخلاص في نداء واحد: Gemini يقرأ الـ PDF/الصورة مباشرة."""
        from google.genai import types
        from ai.prompts import CV_EXTRACTION_PROMPT_TEMPLATE

        prompt = CV_EXTRACTION_PROMPT_TEMPLATE.format(cv_text=_ATTACHED_FILE_NOTE)
        return self._extract([prompt, types.Part.from_bytes(data=data, mime_type=mime_type)], schema)

    def _extract(self, contents, schema: type[BaseModel]) -> BaseModel:
        raw_text = ""
        try:
            client = self._client()
            response = client.models.generate_content(
                model=self._settings.ai_model,
                contents=contents,
                config={
                    "temperature": self._settings.ai_temperature,
                    "response_mime_type": "application/json",
                    "response_schema": _pydantic_to_gemini_schema(schema),
                    "max_output_tokens": 8192,
                },
            )
            raw_text = response.text
            return schema.model_validate(json.loads(raw_text))
        except ValidationError as exc:
            logger.error("Gemini returned data that failed schema validation: %s | raw_response=%s",
                         exc, raw_text[:2000])
            raise AIServiceError("استجابة الذكاء الاصطناعي لم تطابق الشكل المتوقع.") from exc
        except Exception as exc:
            logger.error("Gemini call failed: %s | raw_response=%s", exc, raw_text[:2000])
            raise AIServiceError(f"فشل استدعاء Gemini: {exc}") from exc

    def translate_json(self, data: dict[str, Any], target_language: str = "Arabic") -> dict[str, Any]:
        """يترجم قيم dict إلى اللغة المطلوبة مع الحفاظ على البنية. يرفع AIServiceError عند الفشل."""
        from ai.prompts import TRANSLATION_PROMPT_TEMPLATE

        raw_text = ""
        try:
            client = self._client()
            prompt = TRANSLATION_PROMPT_TEMPLATE.format(
                language=target_language,
                payload=json.dumps(data, ensure_ascii=False),
            )
            response = client.models.generate_content(
                model=self._settings.ai_model,
                contents=prompt,
                config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                    "max_output_tokens": 8192,
                },
            )
            raw_text = response.text
            result = json.loads(raw_text)
            if not isinstance(result, dict):
                raise ValueError("الاستجابة ليست كائن JSON.")
            return result
        except Exception as exc:
            logger.error("Gemini translation failed: %s | raw_response=%s", exc, raw_text[:2000])
            raise AIServiceError(f"فشل ترجمة البيانات: {exc}") from exc

    def parse_search_query(self, query: str):
        """يحوّل طلب بحث بلغة طبيعية إلى CandidateSearchFilters. يرفع AIServiceError عند الفشل."""
        from ai.prompts import NL_SEARCH_PROMPT_TEMPLATE
        from ai.schemas import CandidateSearchFilters

        raw_text = ""
        try:
            client = self._client()
            response = client.models.generate_content(
                model=self._settings.ai_model,
                contents=NL_SEARCH_PROMPT_TEMPLATE.format(query=query[:1000]),
                config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                    "response_schema": _pydantic_to_gemini_schema(CandidateSearchFilters),
                    "max_output_tokens": 1024,
                },
            )
            raw_text = response.text
            return CandidateSearchFilters.model_validate(json.loads(raw_text))
        except ValidationError as exc:
            logger.error("Search filters failed validation: %s | raw_response=%s", exc, raw_text[:1000])
            raise AIServiceError("استجابة الذكاء الاصطناعي لم تطابق الشكل المتوقع.") from exc
        except Exception as exc:
            logger.error("Gemini search parsing failed: %s | raw_response=%s", exc, raw_text[:1000])
            raise AIServiceError(f"فشل فهم طلب البحث: {exc}") from exc

    def generate_interview_questions(self, job_text: str, candidate_text: str):
        """يولّد أسئلة مقابلة مبنية على الوظيفة والمرشح. يرفع AIServiceError عند الفشل."""
        from ai.prompts import INTERVIEW_QUESTIONS_PROMPT_TEMPLATE
        from ai.schemas import InterviewQuestions

        raw_text = ""
        try:
            client = self._client()
            prompt = INTERVIEW_QUESTIONS_PROMPT_TEMPLATE.format(
                job_text=job_text[:4000], candidate_text=candidate_text[:8000]
            )
            response = client.models.generate_content(
                model=self._settings.ai_model,
                contents=prompt,
                config={
                    "temperature": self._settings.ai_temperature,
                    "response_mime_type": "application/json",
                    "response_schema": _pydantic_to_gemini_schema(InterviewQuestions),
                    "max_output_tokens": 4096,
                },
            )
            raw_text = response.text
            return InterviewQuestions.model_validate(json.loads(raw_text))
        except ValidationError as exc:
            logger.error("Interview questions failed validation: %s | raw_response=%s", exc, raw_text[:2000])
            raise AIServiceError("استجابة الذكاء الاصطناعي لم تطابق الشكل المتوقع.") from exc
        except Exception as exc:
            logger.error("Gemini interview generation failed: %s | raw_response=%s", exc, raw_text[:2000])
            raise AIServiceError(f"فشل توليد أسئلة المقابلة: {exc}") from exc

    def analyze_candidate(self, candidate_text: str):
        """يولّد تحليلاً شاملاً للمرشح (مستوى وظيفي، نقاط قوة، فجوات، وظائف مناسبة). يرفع AIServiceError عند الفشل."""
        from ai.prompts import CV_ANALYSIS_PROMPT_TEMPLATE
        from ai.schemas import CandidateAnalysis

        raw_text = ""
        try:
            client = self._client()
            prompt = CV_ANALYSIS_PROMPT_TEMPLATE.format(candidate_text=candidate_text[:8000])
            response = client.models.generate_content(
                model=self._settings.ai_model,
                contents=prompt,
                config={
                    "temperature": self._settings.ai_temperature,
                    "response_mime_type": "application/json",
                    "response_schema": _pydantic_to_gemini_schema(CandidateAnalysis),
                    "max_output_tokens": 2048,
                },
            )
            raw_text = response.text
            return CandidateAnalysis.model_validate(json.loads(raw_text))
        except ValidationError as exc:
            logger.error("Candidate analysis failed validation: %s | raw_response=%s", exc, raw_text[:2000])
            raise AIServiceError("استجابة الذكاء الاصطناعي لم تطابق الشكل المتوقع.") from exc
        except Exception as exc:
            logger.error("Gemini candidate analysis failed: %s | raw_response=%s", exc, raw_text[:2000])
            raise AIServiceError(f"فشل تحليل المرشح: {exc}") from exc

    def analyze_job_description(self, description: str):
        """يحوّل وصف وظيفة غير منظم إلى متطلبات مهيكلة (JobRequirements). يرفع AIServiceError عند الفشل."""
        from ai.prompts import JOB_ANALYSIS_PROMPT_TEMPLATE
        from ai.schemas import JobRequirements

        raw_text = ""
        try:
            client = self._client()
            prompt = JOB_ANALYSIS_PROMPT_TEMPLATE.format(description=description[:6000])
            response = client.models.generate_content(
                model=self._settings.ai_model,
                contents=prompt,
                config={
                    "temperature": self._settings.ai_temperature,
                    "response_mime_type": "application/json",
                    "response_schema": _pydantic_to_gemini_schema(JobRequirements),
                    "max_output_tokens": 4096,
                },
            )
            raw_text = response.text
            return JobRequirements.model_validate(json.loads(raw_text))
        except ValidationError as exc:
            logger.error("Job requirements failed validation: %s | raw_response=%s", exc, raw_text[:2000])
            raise AIServiceError("استجابة الذكاء الاصطناعي لم تطابق الشكل المتوقع.") from exc
        except Exception as exc:
            logger.error("Gemini job analysis failed: %s | raw_response=%s", exc, raw_text[:2000])
            raise AIServiceError(f"فشل تحليل وصف الوظيفة: {exc}") from exc