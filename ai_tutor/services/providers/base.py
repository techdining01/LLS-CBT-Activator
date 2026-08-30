from __future__ import annotations

from abc import ABC, abstractmethod

from app.ai_tutor.schemas import TutorRequest


class AIProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def ask_tutor(self, request: TutorRequest) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def chat(self, prompt: str) -> str:
        """Plain-text chat. Providers may override for efficiency."""
        raise NotImplementedError(f"{self.name} does not support chat()")
