"""محرك مطابقة هجين: يجمع المحرك القاعدي (مهارات/خبرة/موقع/تعليم - مفسَّر بالكامل) مع محرك دلالي
يلتقط تشابهاً معنوياً قد تفوّته المطابقة الحرفية للمهارات (صياغات مختلفة لنفس الخبرة).
يحسب الـ embeddings عند الحاجة فقط عبر EmbeddingService (كاش)."""

from typing import Any

from core.constants import SEMANTIC_DEFAULT_WEIGHT
from matching.base import MatchingEngine
from matching.rule_engine import RuleBasedMatchingEngine
from matching.semantic_engine import SemanticMatchingEngine
from models.candidate import Candidate
from models.job import Job
from services.embedding_service import EmbeddingService


class HybridMatchingEngine(MatchingEngine):
    def __init__(self) -> None:
        self._rule_engine = RuleBasedMatchingEngine()
        self._semantic_engine = SemanticMatchingEngine()
        self._embeddings = EmbeddingService()

    def calculate_match(self, candidate: Candidate, job: Job) -> dict[str, Any]:
        rule_result = self._rule_engine.calculate_match(candidate, job)

        self._embeddings.ensure_candidate_embedding(candidate)
        self._embeddings.ensure_job_embedding(job)
        semantic_result = self._semantic_engine.calculate_match(candidate, job)
        semantic_available = bool(candidate.embedding and job.embedding)

        weights = job.match_weights or {}
        semantic_weight = weights.get("semantic", SEMANTIC_DEFAULT_WEIGHT) if semantic_available else 0.0

        total = rule_result["score"] * (1 - semantic_weight) + semantic_result["score"] * semantic_weight
        total = round(min(total, 100.0), 1)

        breakdown = {**rule_result["breakdown"], "semantic": semantic_result["breakdown"]["semantic"]}
        strengths = rule_result["strengths"] + semantic_result["strengths"]
        gaps = rule_result["gaps"] + (semantic_result["gaps"] if semantic_available else [])

        return {"score": total, "breakdown": breakdown, "strengths": strengths, "gaps": gaps}

    def warm_up_candidates(self, candidates: list[Candidate], job: Job) -> None:
        """يحسب embeddings كل المرشحين بالتوازي قبل حلقة التسجيل (وظيفة ← مرشحون)."""
        self._embeddings.ensure_job_embedding(job)
        self._embeddings.ensure_many_candidate_embeddings(candidates)

    def warm_up_jobs(self, candidate: Candidate, jobs: list[Job]) -> None:
        """يحسب embeddings كل الوظائف بالتوازي قبل حلقة التسجيل (مرشح ← وظائف)."""
        self._embeddings.ensure_candidate_embedding(candidate)
        self._embeddings.ensure_many_job_embeddings(jobs)