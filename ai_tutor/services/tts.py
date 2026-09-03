from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pyttsx3


class TutorTTS:
    """
    Local desktop TTS service.

    pyttsx3 on Windows uses SAPI via COM (STA), which requires
    CoInitialize on the calling thread. We run it in a dedicated
    thread via asyncio.to_thread so each call gets a fresh engine
    with proper COM initialisation.
    """

    def _generate_wav_sync(
        self,
        text: str,
        output_path: str,
        rate: int = 175,
        volume: float = 1.0,
    ) -> None:
        # CoInitialize for Windows COM / SAPI
        try:
            import pythoncom  # type: ignore
            pythoncom.CoInitialize()
        except Exception:
            pass

        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", rate)
            engine.setProperty("volume", volume)
            engine.save_to_file(text, output_path)
            engine.runAndWait()
        finally:
            try:
                engine.stop()
            except Exception:
                pass
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    async def generate(
        self,
        text: str,
        rate: int = 175,
        volume: float = 1.0,
    ) -> Path:

        text = text.strip()
        if not text:
            raise ValueError("Text cannot be empty.")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            output_path = Path(tmp.name)

        await asyncio.to_thread(
            self._generate_wav_sync,
            text,
            str(output_path),
            rate,
            volume,
        )

        return output_path