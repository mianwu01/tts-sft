"""Tests for tts_sft.sft_formatting."""
from __future__ import annotations

from tts_sft.prompts import DEFAULT_MATH_PROMPT
from tts_sft.sft_formatting import build_sft_example


def test_build_sft_example_basic():
    ex = build_sft_example(
        example_id="x1",
        question="What is 2 + 2?",
        response="2 + 2 = \\boxed{4}",
        source="raw_self_sft",
    )
    assert ex["id"] == "x1"
    assert ex["source"] == "raw_self_sft"
    assert len(ex["messages"]) == 2

    user, assistant = ex["messages"]
    assert user["role"] == "user"
    assert "What is 2 + 2?" in user["content"]
    assert "Please solve the following math problem" in user["content"]

    assert assistant["role"] == "assistant"
    assert assistant["content"] == "2 + 2 = \\boxed{4}"


def test_default_prompt_template_used():
    ex = build_sft_example(
        example_id="x2",
        question="Q?",
        response="A",
        source="src",
    )
    expected = DEFAULT_MATH_PROMPT.replace("{question}", "Q?")
    assert ex["messages"][0]["content"] == expected


def test_custom_prompt_template():
    template = "Solve this:\n{question}\nEnd."
    ex = build_sft_example(
        example_id="x3",
        question="2+2",
        response="4",
        source="src",
        prompt_template=template,
    )
    assert ex["messages"][0]["content"] == "Solve this:\n2+2\nEnd."


def test_preserves_thinking_tags():
    response = "<think>let me work this out</think>\n\nFinal: \\boxed{7}"
    ex = build_sft_example(
        example_id="t1",
        question="?",
        response=response,
        source="raw_self_sft",
    )
    # Critical: thinking sections must not be stripped.
    assert "<think>" in ex["messages"][1]["content"]
    assert ex["messages"][1]["content"] == response


def test_extra_metadata_attached():
    ex = build_sft_example(
        example_id="m1",
        question="?",
        response="!",
        source="src",
        extra_metadata={"foo": "bar"},
    )
    assert ex["metadata"] == {"foo": "bar"}


def test_no_metadata_when_unset():
    ex = build_sft_example(
        example_id="m2",
        question="?",
        response="!",
        source="src",
    )
    assert "metadata" not in ex


def test_source_tags_differ():
    raw = build_sft_example(example_id="a", question="?", response="!", source="raw_self_sft")
    se = build_sft_example(example_id="b", question="?", response="!", source="squeeze_evolve_sft")
    assert raw["source"] == "raw_self_sft"
    assert se["source"] == "squeeze_evolve_sft"
