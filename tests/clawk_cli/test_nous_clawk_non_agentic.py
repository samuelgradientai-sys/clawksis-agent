"""Tests for the Nous-Clawksis-3/4 non-agentic warning detector.



Prior to this check, the warning fired on any model whose name contained

``"clawk"`` anywhere (case-insensitive). That false-positived on unrelated

local Modelfiles such as ``clawk-brain:qwen3-14b-ctx16k`` — a tool-capable

Qwen3 wrapper that happens to live under the "clawk" tag namespace.



``is_nous_clawk_non_agentic`` should only match the actual Nous Research

Clawksis-3 / Clawksis-4 chat family.

"""

from __future__ import annotations


import pytest


from clawk_cli.model_switch import (
    _CLAWK_MODEL_WARNING,
    _check_clawk_model_warning,
    is_nous_clawk_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "NousResearch/Clawksis-3-Llama-3.1-70B",
        "NousResearch/Clawksis-3-Llama-3.1-405B",
        "clawk-3",
        "Clawksis-3",
        "clawk-4",
        "clawk-4-405b",
        "clawk_4_70b",
        "openrouter/clawk3:70b",
        "openrouter/nousresearch/clawk-4-405b",
        "NousResearch/Clawksis3",
        "clawk-3.1",
    ],
)
def test_matches_real_nous_clawk_chat_models(model_name: str) -> None:

    assert is_nous_clawk_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous Clawksis 3/4"
    )

    assert _check_clawk_model_warning(model_name) == _CLAWK_MODEL_WARNING


@pytest.mark.parametrize(
    "model_name",
    [
        # Kyle's local Modelfile — qwen3:14b under a custom tag
        "clawk-brain:qwen3-14b-ctx16k",
        "clawk-brain:qwen3-14b-ctx32k",
        "clawk-honcho:qwen3-8b-ctx8k",
        # Plain unrelated models
        "qwen3:14b",
        "qwen3-coder:30b",
        "qwen2.5:14b",
        "claude-opus-4-6",
        "anthropic/claude-sonnet-4.5",
        "gpt-5",
        "openai/gpt-4o",
        "google/gemini-2.5-flash",
        "deepseek-chat",
        # Non-chat Clawksis models we don't warn about
        "clawk-llm-2",
        "clawk2-pro",
        "nous-clawk-2-mistral",
        # Edge cases
        "",
        "clawk",  # bare "clawk" isn't the 3/4 family
        "clawk-brain",
        "brain-clawk-3-impostor",  # "3" not preceded by /: boundary
    ],
)
def test_does_not_match_unrelated_models(model_name: str) -> None:

    assert not is_nous_clawk_non_agentic(model_name), (
        f"expected {model_name!r} NOT to be flagged as Nous Clawksis 3/4"
    )

    assert _check_clawk_model_warning(model_name) == ""


def test_none_like_inputs_are_safe() -> None:

    assert is_nous_clawk_non_agentic("") is False

    # Defensive: the helper shouldn't crash on None-ish falsy input either.

    assert _check_clawk_model_warning("") == ""
