from __future__ import annotations

from abc import ABC, abstractmethod

from ai_tutor.schemas import ChatMessage, TutorRequest


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
    async def chat(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Chat with structured message + conversation history + optional system prompt.

        Providers forward history natively when possible; otherwise
        flatten locally for APIs that only accept a bare prompt string.

        Remote/cloud providers MAY ignore system_prompt when the remote
        endpoint applies its own system prompt (to avoid double-wrapping).
        """
        raise NotImplementedError(f"{self.name} does not support chat()")
