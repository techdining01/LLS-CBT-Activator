from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException


from ai_tutor.schemas import (
    TutorRequest,
    TutorResponse,
    TutorSpeakRequest,
    ChatRequest,
    ChatResponse,
    RawChatRequest,
)

from ai_tutor.services.providers.provider_manager import (
    AIProviderManager,
)

from ai_tutor.services.providers.gemini import (
    GeminiProvider,
)

from ai_tutor.services.providers.ollama import (
    OllamaProvider,
)

from ai_tutor.services.providers.remote_server import (
    RemoteServerProvider,
)


from fastapi.responses import FileResponse


from dotenv import load_dotenv


def _bootstrap_env():
    """Load .env from sensible locations BEFORE any provider is constructed.

    Runs at module-import time (before provider constructors) so that
    GEMINI_API_KEY / LICENSE_SERVER_URL / OLLAMA_BASE_URL are visible
    to every provider singleton whether we run in dev, in a PyInstaller
    frozen EXE, or as a Render server worker.
    """
    candidates = []
    if getattr(sys, "frozen", False):
        # === PyInstaller frozen EXE (desktop) ===
        meipass = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
        if meipass.is_dir():
            candidates.append(meipass / ".env")
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / ".env")
        if meipass.is_dir() and meipass.name == "_internal":
            candidates.append(meipass.parent / ".env")
    else:
        # === Development / Render server ===
        # router.py lives at app/ai_tutor/router.py
        #   parents[0] = app/ai_tutor
        #   parents[1] = app
        #   parents[2] = PROJECT ROOT (mock_cbt)    <-- .env lives here
        #   parents[3] = .. (too far up)
        try:
            project_root = Path(__file__).resolve().parents[2]
        except (IndexError, NameError, TypeError):
            project_root = Path.cwd()
        candidates.append(project_root / ".env")
        candidates.append(Path.cwd() / ".env")
        # Also try 1 level up (in case someone runs tests from a subfolder)
        candidates.append(Path.cwd().parent / ".env")

    for candidate in candidates:
        if not candidate or not candidate.is_file():
            continue
        try:
            # On Windows, python-dotenv defaults to the OEM code page;
            # explicit utf-8 ensures keys with non-ASCII edge cases load.
            ok = load_dotenv(candidate, override=False, encoding="utf-8")
            if ok:
                print(f"[env:router] Loaded {candidate}", flush=True)
        except Exception as exc:
            print(f"[env:router] Failed to load {candidate}: {exc}", flush=True)

    # Pin SSL CA bundle to certifi so httpx/requests/google-genai can verify
    # Gemini / Render / Ollama HTTPS endpoints.
    try:
        import certifi
        pem = Path(certifi.where())
        if pem and pem.is_file():
            for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
                os.environ.setdefault(var, str(pem))
    except Exception as exc:
        print(f"[env:router] certifi fix skipped: {exc}", flush=True)


_bootstrap_env()


router = APIRouter(
    prefix="/api/v1/tutor",
    tags=["AI Tutor"],
)


# Provider priority for DESKTOP mode (user has their own .env with GEMINI_API_KEY,
# or falls back to the Render cloud proxy, or finally falls back to local Ollama):
#   1. GeminiProvider     - uses local GEMINI_API_KEY directly (fastest, user's own quota)
#   2. RemoteServerProvider - proxies through Render (hosted Gemini key)
#   3. OllamaProvider     - fully offline via a locally installed Ollama server
#
# For the dedicated AI server on Render, only Gemini is needed.
_running_as_ai_server = os.getenv("AI_PROVIDER_ROLE", "").lower() == "server"
if _running_as_ai_server:
    _providers = [GeminiProvider(), OllamaProvider()]
else:
    _providers = [
        GeminiProvider(),
        RemoteServerProvider(),
        OllamaProvider(),
    ]
provider_manager = AIProviderManager(providers=_providers)


@router.get("/health")
async def tutor_health():
    return {
        "success": True,
        "service": "AI Tutor",
        "providers": provider_manager.health(),
    }


@router.get("/status")
async def tutor_status():
    """Lightweight status check: tells the frontend which AI backend is active."""
    health = provider_manager.health()
    active = next(
        (name for name, info in health.items() if info.get("available")),
        None,
    )
    return {
        "success": True,
        "active_provider": active,
        "online": active is not None,
        "providers": health,
    }


@router.post(
    "/ask",
    response_model=TutorResponse,
)
async def ask_tutor(
    request: TutorRequest,
):

    try:
        provider_name, result = await provider_manager.ask_tutor(request)

        greeting = result.get(
            "greeting",
            "",
        )

        explanation = result.get(
            "explanation",
            "",
        )

        steps = result.get(
            "steps",
            [],
        )

        hint = result.get(
            "hint",
            "",
        )

        encouragement = result.get(
            "encouragement",
            "",
        )

        follow_up = result.get(
            "follow_up_question",
            "",
        )

        parts: list[str] = []

        if greeting:
            parts.append(greeting)

        if explanation:
            parts.append(explanation)

        if steps:
            parts.append(
                "\n".join(f"{index + 1}. {step}" for index, step in enumerate(steps))
            )

        if hint:
            parts.append(f"Hint: {hint}")

        if encouragement:
            parts.append(encouragement)

        if follow_up:
            parts.append(f"Think about this: {follow_up}")

        answer = "\n\n".join(parts)

        return TutorResponse(
            success=True,
            answer=answer,
            provider=provider_name,
            greeting=greeting,
            explanation=explanation,
            steps=steps,
            hint=hint,
            encouragement=encouragement,
            follow_up_question=follow_up,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI Tutor is temporarily unavailable. All configured providers failed."
            ),
        ) from exc


@router.post("/speak")
async def speak_tutor(request: TutorSpeakRequest):

    try:
        from ai_tutor.services.tts import TutorTTS
        from fastapi.responses import Response
        import asyncio

        tts_service = TutorTTS()
        audio_path = await tts_service.generate(text=request.text)

        # Small delay to ensure pyttsx3 has fully flushed the file
        await asyncio.sleep(0.1)

        audio_bytes = audio_path.read_bytes()

        # Clean up temp file immediately after reading
        try:
            audio_path.unlink()
        except OSError:
            pass

        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={"Cache-Control": "no-store"},
        )

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Local AI Tutor speech generation failed: {exc}",
        ) from exc


CHAT_SYSTEM_PROMPT = """
You are a friendly, wise, and encouraging AI companion for secondary school students.

Your role is to have enriching conversations on any educational or life topic the student brings up.
Topics include but are not limited to: education, science, history, technology, religion, lifestyle,
social issues, adventure, career, health, and current events.

CORE BEHAVIOUR RULES:

1. ENCOURAGE GRIT AND EFFORT.
   Always remind students that success comes from consistent hard work, not just talent.
   Reference real successful people relevant to the topic when appropriate
   (e.g. Elon Musk for technology, Wole Soyinka for literature, Aliko Dangote for business,
   Marie Curie for science, Nelson Mandela for perseverance, etc.).

2. WARN AGAINST BAD HABITS.
   If the student mentions or implies drug use, violence, vulgarity, laziness, cheating,
   or any destructive behaviour, respond with firm but kind redirection.
   Explain the consequences clearly and suggest a better path.

3. REJECT VULGAR OR INAPPROPRIATE LANGUAGE.
   If the student uses vulgar, offensive, or sexually explicit language, do NOT engage with it.
   Politely but firmly decline, explain why such language is harmful, and redirect the conversation.

4. INSPIRE WITH REAL EXAMPLES.
   When discussing any topic, weave in brief stories or facts about real people who succeeded
   through hard work, faith, resilience, or curiosity — matching the context of the conversation.

5. BE WARM, CLEAR, AND AGE-APPROPRIATE.
   Write as if speaking to a bright secondary school student. Avoid jargon.
   Be conversational, not lecture-like.

6. KEEP RESPONSES FOCUSED.
   Give a clear, helpful reply. Do not ramble. End with a thought-provoking question
   or an encouraging statement to keep the student engaged.

Respond in plain text only. No markdown, no bullet symbols, no JSON.
"""


@router.post("/chat", response_model=ChatResponse)
async def general_chat(request: ChatRequest):
    try:
        # Pass structured (message, history) + the system prompt to the manager.
        # Local providers (Gemini, Ollama) flatten locally with the system prompt.
        # RemoteServerProvider skips system_prompt and forwards cleanly to Render's
        # /chat endpoint, preventing double-wrapping and preserving chat history.
        provider_name, reply = await provider_manager.chat(
            request.message,
            history=request.history,
            system_prompt=CHAT_SYSTEM_PROMPT,
        )

        return ChatResponse(success=True, reply=reply, provider=provider_name)

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="General Knowledge AI is temporarily unavailable.",
        ) from exc


@router.post("/chat_raw", response_model=ChatResponse)
async def general_chat_raw(request: RawChatRequest):
    try:
        provider_name, reply = await provider_manager.chat(
            request.prompt,
            history=[],
            system_prompt=None,
        )
        return ChatResponse(success=True, reply=reply, provider=provider_name)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="General Knowledge AI is temporarily unavailable.",
        ) from exc
