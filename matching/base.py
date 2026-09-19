"""واجهة مجردة لأي محرك مطابقة."""

from abc import ABC, abstractmethod
from typing import Any

from models.candidate import Candidate
from models.job import Job


class MatchingEngine(ABC):
    @abstractmethod
    def calculate_match(self, candidate: Candidate, job: Job) -> dict[str, Any]:
        """يرجع dict فيه: score (0-100)، breakdown لكل معيار، strengths، gaps."""
        raise NotImplementedError
