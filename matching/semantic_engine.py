"""محرك مطابقة دلالي (Semantic): يقيس التشابه المعنوي الكامل بين ملف المرشح ووصف الوظيفة عبر
Embeddings، بعكس المحرك القاعدي الذي يقارن قوائم مهارات حرفية فقط. لا يُستخدم بمفرده للقرار،
بل يُدمج ضمن HybridMatchingEngine. يفترض أن الـ embedding محسوب مسبقاً (عبر EmbeddingService)."""

from typing import Any

from ai.embeddings import cosine_similarity
from matching.base import MatchingEngine
from models.candidate import Candidate
from models.job import Job


class SemanticMatchingEngine(MatchingEngine):
    def calculate_match(self, candidate: Candidate, job: Job) -> dict[str, Any]:
        if not candidate.embedding or not job.embedding:
            return {
                "score": 0.0,
                "breakdown": {"semantic": 0.0},
                "strengths": [],
                "gaps": ["⚠ لم يتم حساب المطابقة الدلالية (لا يوجد GEMINI_API_KEY أو فشل الحساب)."],
            }

        similarity = cosine_similarity(candidate.embedding, job.embedding)
        score = round(max(similarity, 0.0) * 100, 1)

        strengths = ["✓ تشابه معنوي قوي بين خبرة المرشح ومتطلبات الوظيفة"] if score >= 75 else []
        gaps = ["⚠ تشابه معنوي منخفض بين ملف المرشح ووصف الوظيفة"] if score < 40 else []

        return {"score": score, "breakdown": {"semantic": score}, "strengths": strengths, "gaps": gaps}
    