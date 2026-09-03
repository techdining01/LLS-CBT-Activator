from __future__ import annotations

import logging

from ai_tutor.schemas import ChatMessage, TutorRequest
from ai_tutor.services.providers.base import AIProvider
from ai_tutor.services.response_validator import (
    validate_tutor_result,
)


logger = logging.getLogger(__name__)


class AIProviderManager:
    def __init__(
        self,
        providers: list[AIProvider],
    ):
        self.providers = providers

    async def ask_tutor(
        self,
        request: TutorRequest,
    ) -> tuple[str, dict]:

        last_error: Exception | None = None

        for provider in self.providers:
            if not provider.available:
                logger.info("Skipping unavailable provider: %s", provider.name)
                continue

            try:
                result = await provider.ask_tutor(request)
                validated = validate_tutor_result(result)
                logger.info("AI provider succeeded: %s", provider.name)
                return (provider.name, validated.model_dump())

            except Exception as exc:
                last_error = exc
                error_type = type(exc).__name__
                logger.warning("AI provider failed: %s - %s (%s)", provider.name, exc, error_type)
                continue

        if last_error is not None:
            raise RuntimeError("All AI providers failed.") from last_error
        raise RuntimeError("No AI providers are available.")

    async def chat(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
        system_prompt: str | None = None,
    ) -> tuple[str, str]:
        """Send a structured chat message + history + optional system prompt.
        Returns (provider_name, reply_text)."""

        last_error: Exception | None = None

        for provider in self.providers:
            if not provider.available:
                logger.info("Skipping unavailable chat provider: %s", provider.name)
                continue

            try:
                reply = await provider.chat(message, history=history, system_prompt=system_prompt)
                logger.info("Chat provider succeeded: %s", provider.name)
                return (provider.name, reply)

            except Exception as exc:
                last_error = exc
                error_type = type(exc).__name__
                logger.warning("Chat provider failed: %s - %s (%s)", provider.name, exc, error_type)
                continue

        if last_error is not None:
            raise RuntimeError("All chat providers failed.") from last_error
        raise RuntimeError("No chat providers are available.")

    def health(self) -> dict:

        return {
            provider.name: {
                "available": provider.available,
            }
            for provider in self.providers
        }
