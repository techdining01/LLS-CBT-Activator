from __future__ import annotations

from fastapi import APIRouter, HTTPException


from app.ai_tutor.schemas import (
    TutorRequest,
    TutorResponse,
    TutorSpeakRequest,
    ChatRequest,
    ChatResponse,
)

from app.ai_tutor.services.providers.provider_manager import (
    AIProviderManager,
)

from app.ai_tutor.services.providers.gemini import (
    GeminiProvider,
)

from app.ai_tutor.services.providers.ollama import (
    OllamaProvider,
)

from pathlib import Path

from fastapi.responses import FileResponse



router = APIRouter(
    prefix="/api/v1/tutor",
    tags=["AI Tutor"],
)


provider_manager = AIProviderManager(
    providers=[
        GeminiProvider(),
        OllamaProvider(),
    ]
)


@router.get("/health")
async def tutor_health():

    return {
        "success": True,
        "service": "AI Tutor",
        "providers": provider_manager.health(),
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
        from app.ai_tutor.services.tts import TutorTTS
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
        history_text = ""
        for msg in request.history[-10:]:
            role = "Student" if msg.role == "user" else "AI"
            history_text += f"{role}: {msg.content}\n"

        prompt = f"{CHAT_SYSTEM_PROMPT}\nCONVERSATION SO FAR:\n{history_text}Student: {request.message}\nAI:"

        provider_name, reply = await provider_manager.chat(prompt)

        return ChatResponse(success=True, reply=reply, provider=provider_name)

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="General Knowledge AI is temporarily unavailable.",
        ) from exc