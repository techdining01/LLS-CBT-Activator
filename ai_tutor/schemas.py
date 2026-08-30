from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class TutorOption(BaseModel):
    label: str
    text: str


class TutorRequest(BaseModel):
    subject: str
    question: str

    options: list[TutorOption] = Field(default_factory=list)

    correct_answer: str = ""

    student_answer: str = ""

    explanation: str = ""

    @field_validator("subject", "question")
    @classmethod
    def validate_required_text(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError("This field cannot be empty.")

        return value


class TutorAIResult(BaseModel):
    greeting: str = ""
    explanation: str = ""

    steps: list[str] = Field(default_factory=list)

    hint: str = ""

    encouragement: str = ""

    follow_up_question: str = ""

    @field_validator("steps")
    @classmethod
    def clean_steps(
        cls,
        value: list[str],
    ) -> list[str]:
        return [
            step.strip() for step in value if isinstance(step, str) and step.strip()
        ]


class TutorResponse(BaseModel):
    success: bool

    answer: str

    provider: str = ""

    greeting: str = ""

    explanation: str = ""

    steps: list[str] = Field(default_factory=list)

    hint: str = ""

    encouragement: str = ""

    follow_up_question: str = ""


class TutorSpeakRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def validate_text(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Text cannot be empty.")

        return value


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty.")
        return value


class ChatResponse(BaseModel):
    success: bool
    reply: str
    provider: str = ""