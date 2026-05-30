"""Prompt templates for math problem solving."""
from __future__ import annotations

DEFAULT_MATH_PROMPT = (
    "Please solve the following math problem. Show your reasoning and "
    "put the final answer in \\boxed{}.\n\nProblem:\n{question}"
)


def build_math_user_message(question: str, template: str = DEFAULT_MATH_PROMPT) -> str:
    """Render the math prompt template with a given question.

    The template is expected to contain a single ``{question}`` placeholder.
    Other braces in the template are left untouched.
    """
    return template.replace("{question}", question)
