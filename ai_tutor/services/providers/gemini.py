from __future__ import annotations

import asyncio
import json
import os

from google import genai

from ai_tutor.schemas import ChatMessage, TutorRequest
from ai_tutor.services.providers.base import AIProvider


class GeminiProvider(AIProvider):
    def __init__(self):
        self.api_key = None
        self.client = None
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.timeout = float(os.getenv("GEMINI_TIMEOUT", "45"))
        self._ensure_client()

    def _ensure_client(self):
        """Dynamically initialize or refresh Gemini client if API key is present."""
        key = os.getenv("GEMINI_API_KEY")
        if key and (self.client is None or key != self.api_key):
            self.api_key = key
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as err:
                print(f"[GeminiProvider] Client initialization error: {err}")
                self.client = None

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def available(self) -> bool:
        self._ensure_client()
        return self.client is not None and bool(self.api_key)

    async def ask_tutor(
        self,
        request: TutorRequest,
    ) -> dict:
        self._ensure_client()
        if not self.available:
            raise RuntimeError("Gemini provider is not configured. Missing GEMINI_API_KEY.")

        options_text = "\n".join(
            f"{option.label}. {option.text}" for option in request.options
        )

        prompt = self._build_prompt(
            request=request,
            options_text=options_text,
        )

        response = await asyncio.wait_for(
            self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
            ),
            timeout=self.timeout,
        )

        raw = response.text.strip()
        return self._parse_response(raw)

    async def chat(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
        system_prompt: str | None = None,
    ) -> str:
        self._ensure_client()
        if not self.available:
            raise RuntimeError("Gemini provider is not configured. Missing GEMINI_API_KEY.")

        prompt = self._flatten_chat(message, history, system_prompt)

        response = await asyncio.wait_for(
            self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
            ),
            timeout=self.timeout,
        )
        return response.text.strip()

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
        options_text: str,
    ) -> str:
        return f"""
You are an excellent secondary-school teacher
helping a student understand a CBT examination question.

CRITICAL RULE:
The CORRECT ANSWER supplied by the CBT system is authoritative.
You MUST NOT change it, recalculate it, reinterpret it,
or choose another option.
Your job is to explain the supplied correct answer.

If the student's answer differs from the CORRECT ANSWER,
clearly explain why the student's answer is incorrect and
why the supplied correct answer is correct.

Never state the student's answer as the correct answer.

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

Give a clear, friendly teaching explanation.
If the student selected the wrong answer:
- explain why their choice is wrong
- explain why the correct answer is correct
- do not embarrass the student

If the question requires reasoning, explain the reasoning step by step.

IMPORTANT: For the "steps" field:
- Only include actual, meaningful step-by-step reasoning if the question requires it (mathematics, calculations, logical reasoning, etc.)
- Each step should be a complete, clear explanation of one part of the solution
- If the question does NOT require step-by-step reasoning, return an empty array: []

CRITICAL: You MUST provide content for ALL fields. Do not leave any field empty:
- "greeting": Always provide a short, friendly greeting appropriate for the context
- "explanation": Always provide a clear, detailed explanation of the answer
- "steps": provide meaningful step-by-step reasoning in an array 
- "hint": Always provide a helpful memory aid or tip related to the question
- "encouragement": Always provide encouraging words appropriate for the student's performance
- "follow_up_question": Always provide a thought-provoking follow-up question to deepen understanding

Return ONLY valid JSON.

Use exactly this structure:
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
    def _parse_response(raw: str) -> dict:
        if raw.startswith("```json"):
            raw = raw[7:]
        elif raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Gemini returned an invalid response.")
        return result
