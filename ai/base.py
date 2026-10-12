
from abc import ABC, abstractmethod

from pydantic import BaseModel


class AIProvider(ABC):

    @abstractmethod
    def extract_structured(self, text: str, schema: type[BaseModel]) -> BaseModel:
        raise NotImplementedError
