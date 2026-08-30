from __future__ import annotations

from app.ai_tutor.schemas import TutorAIResult


def validate_tutor_result(
    result: dict,
) -> TutorAIResult:

    if not isinstance(result, dict):
        raise ValueError("AI provider returned a non-object response.")

    validated = TutorAIResult.model_validate(result)

    if not (
        validated.explanation or validated.greeting or validated.steps or validated.hint
    ):
        raise ValueError("AI provider returned an empty tutor response.")

    return validated
