"""validate_requested_model must treat local Ollama as a first-class provider.

Regression: `_PROVIDER_ALIASES` maps "ollama" -> "custom", so before the fix an
ollama switch fell into the generic custom probe path and was REJECTED
(accepted=False) whenever the live /v1/models probe hiccupped — even though the
user picked the model from a list populated live from the running daemon. That
left the dashboard "Switch Model" dialog unable to switch to a local model.
"""

from unittest.mock import patch

from clawk_cli.models import validate_requested_model


def test_ollama_accepts_even_when_endpoint_unreachable():
    """A local ollama switch must NOT be rejected when the probe can't reach it."""

    # Force the probe to look unreachable (models=None) — the custom path would
    # return accepted=False here; the ollama branch must still accept.
    with patch("clawk_cli.models.probe_api_models", return_value={"models": None}):
        result = validate_requested_model(
            "phi3:3.8b",
            "ollama",
            api_key="ollama",
            base_url="http://localhost:11434/v1",
            api_mode="chat_completions",
        )

    assert result["accepted"] is True
    assert result["persist"] is True
    assert result["recognized"] is False


def test_ollama_recognizes_model_present_in_endpoint():
    """When the daemon lists the model, recognized=True."""

    with patch(
        "clawk_cli.models.probe_api_models",
        return_value={"models": ["phi3:3.8b", "llama3:8b"]},
    ):
        result = validate_requested_model(
            "phi3:3.8b",
            "ollama",
            api_key="ollama",
            base_url="http://localhost:11434/v1",
            api_mode="chat_completions",
        )

    assert result["accepted"] is True
    assert result["recognized"] is True


def test_custom_unreachable_still_rejected():
    """Guard against over-broadening: a real custom endpoint that is unreachable
    must still be rejected (chat_completions mode), proving we only special-cased
    ollama."""

    with patch(
        "clawk_cli.models.probe_api_models",
        return_value={"models": None, "probed_url": "http://x/v1/models"},
    ):
        result = validate_requested_model(
            "some-model",
            "custom",
            api_key="x",
            base_url="http://unreachable.local/v1",
            api_mode="chat_completions",
        )

    assert result["accepted"] is False
