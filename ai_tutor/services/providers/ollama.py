from __future__ import annotations

import json
import os

import httpx

from ai_tutor.schemas import ChatMessage, TutorRequest
from ai_tutor.services.providers.base import AIProvider


class OllamaProvider(AIProvider):
    def __init__(self):
        self.base_url = os.getenv(
            "OLLAMA_BASE_URL",
            "http://127.0.0.1:11434",
        ).rstrip("/")

        self.model = os.getenv(
            "OLLAMA_MODEL",
            "qwen2.5:0.5b-instruct",
        )

        self.timeout = float(
            os.getenv(
                "OLLAMA_TIMEOUT",
                "90",
            )
        )

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def available(self) -> bool:
        # Synchronous port probe — avoids async overhead in the health check path.
        import socket
        try:
            host = self.base_url.split("://")[-1].split("/")[0]
            addr, port_str = (host.rsplit(":", 1) + ["11434"])[:2]
            with socket.create_connection((addr, int(port_str)), timeout=1):
                return True
        except OSError:
            return False

    async def ask_tutor(
        self,
        request: TutorRequest,
    ) -> dict:

        prompt = self._build_prompt(request)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.2,
            },
        }

        async with httpx.AsyncClient(
            timeout=self.timeout,
        ) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )

            response.raise_for_status()

        data = response.json()

        raw = data.get("response", "").strip()

        if not raw:
            raise RuntimeError("Ollama returned an empty response.")

        return self._parse_response(raw)

    async def chat(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
        system_prompt: str | None = None,
    ) -> str:
        prompt = self._flatten_chat(message, history, system_prompt)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.7},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
        return response.json().get("response", "").strip()

    @staticmethod
    def _flatten_chat(
        message: str,
        history: list[ChatMessage] | None,
        system_prompt: str | None = None,
    ) -> str:
        """Flatten structured (message, history, system_prompt) into a plain-text prompt."""
        lines: list[str] = []
        if system_prompt:
            lines.append(system_prompt.strip())
            lines.append("")
        for msg in (history or [])[-10:]:
            role = "Student" if msg.role == "user" else "AI"
            lines.append(f"{role}: {msg.content}")
        lines.append(f"Student: {message}")
        lines.append("AI:")
        return "\n".join(lines)

    def _build_prompt(
        self,
        request: TutorRequest,
    ) -> str:

        options_text = "\n".join(
            f"{option.label}. {option.text}" for option in request.options
        )

        return f"""
You are a secondary-school CBT tutor.

Your job is to help the student understand the
examination question, not simply give an answer.

The supplied correct answer is authoritative.
DO NOT change it.

SUBJECT:
{request.subject}

QUESTION:
{request.question}

OPTIONS:
{options_text or "No options supplied"}

STUDENT'S ANSWER:
{request.student_answer or "No answer selected"}

CORRECT ANSWER:
{request.correct_answer or "Not supplied"}

STORED EXPLANATION:
{request.explanation or "No stored explanation available"}

Instructions:

1. Explain the answer clearly.
2. If the student selected the wrong answer,
   explain why it is wrong.
3. Explain why the correct answer is correct.
4. If reasoning is required, explain it step by step.
5. Be friendly and encouraging.
6. Do not embarrass the student.
7. Do not invent facts.
8. Do not change the supplied correct answer.

IMPORTANT: For the "steps" field:
- Only include actual, meaningful step-by-step reasoning if the question requires it (mathematics, calculations, logical reasoning, etc.)
- Each step should be a complete, clear explanation of one part of the solution
- Example of good steps: ["First, identify the formula needed", "Substitute the given values into the formula", "Calculate the result step by step", "Verify the answer makes sense"]
- If the question does NOT require step-by-step reasoning, return an empty array: []
- NEVER use placeholder text like "step one", "step two" - either give real steps or return []

CRITICAL: You MUST provide content for ALL fields. Do not leave any field empty:
- "greeting": Always provide a short, friendly greeting appropriate for the context
- "explanation": Always provide a clear, detailed explanation of the answer
- "steps": provide meaningful step-by-step reasoning in an array
- "hint": Provide a helpful memory aid or tip related to the question
- "encouragement": Always provide encouraging words appropriate for the student's performance
- "follow_up_question": Always provide a thought-provoking follow-up question to deepen understanding

Return ONLY valid JSON with exactly these fields:

{{
    "greeting": "short friendly greeting",
    "explanation": "clear explanation",
    "steps": [],
    "hint": "helpful memory aid or tip",
    "encouragement": "encouraging words",
    "follow_up_question": "thought-provoking follow-up question"
}}
"""

    @staticmethod
    def _parse_response(
        raw: str,
    ) -> dict:

        raw = raw.strip()

        if raw.startswith("```json"):
            raw = raw[7:]

        elif raw.startswith("```"):
            raw = raw[3:]

        if raw.endswith("```"):
            raw = raw[:-3]

        raw = raw.strip()

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama returned invalid JSON.") from exc

        if not isinstance(result, dict):
            raise RuntimeError("Ollama returned an invalid object.")

        return result
