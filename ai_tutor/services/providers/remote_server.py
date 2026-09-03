from __future__ import annotations

import os
import socket
import httpx

from ai_tutor.schemas import ChatMessage, TutorRequest
from ai_tutor.services.providers.base import AIProvider

# Quick connectivity probe timeout (seconds)
_PROBE_TIMEOUT = 2.0


class RemoteServerProvider(AIProvider):
    """
    Proxies AI requests to the Render cloud server which holds the Gemini API key.
    Falls back gracefully when the desktop machine is offline.
    """

    def __init__(self):
        self.server_url = os.getenv(
            "LICENSE_SERVER_URL",
            "https://lls-cbt-activator.onrender.com",
        ).rstrip("/")
        self.timeout = float(os.getenv("AI_SERVER_TIMEOUT", "25"))

    @property
    def name(self) -> str:
        return "cloud-ai"

    @property
    def available(self) -> bool:
        """Fast synchronous TCP probe — avoids blocking the async event loop."""
        if not self.server_url:
            return False
        try:
            host = self.server_url.split("://")[-1].split("/")[0]
            addr, port_str = (host.rsplit(":", 1) + ["443"])[:2]
            with socket.create_connection((addr, int(port_str)), timeout=1.5):
                return True
        except OSError:
            return False

    async def ask_tutor(self, request: TutorRequest) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.server_url}/api/v1/tutor/ask",
                json=request.model_dump(),
            )
            response.raise_for_status()

        data = response.json()
        return {
            "greeting": data.get("greeting", ""),
            "explanation": data.get("explanation", ""),
            "steps": data.get("steps", []),
            "hint": data.get("hint", ""),
            "encouragement": data.get("encouragement", ""),
            "follow_up_question": data.get("follow_up_question", ""),
        }

    async def chat(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Forward structured (message, history) to the cloud /chat endpoint.

        NOTE: system_prompt is intentionally NOT forwarded here — the remote
        Render server applies its own CHAT_SYSTEM_PROMPT in its /chat handler.
        Forwarding a local system_prompt would cause double-wrapping.
        """
        payload = {
            "message": message,
            "history": [
                {"role": m.role, "content": m.content}
                for m in (history or [])
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.server_url}/api/v1/tutor/chat",
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        return (data.get("reply") or "").strip()
