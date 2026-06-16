"""The 64K minimum-context guard must exempt LOCAL models.

Local backends (Ollama / LM Studio / localhost endpoints) routinely ship a
context window below the 64K minimum. Hard-failing them bricks the agent and
makes the cookbook/local-model flow unusable, so init_agent warns and runs
instead of raising — while cloud providers stay subject to the strict minimum.
This tests the decision helper that gates that behavior.
"""

import pytest

from agent.agent_init import _model_is_local_endpoint


@pytest.mark.parametrize(
    "provider,base_url",
    [
        ("ollama", ""),
        ("ollama", "http://localhost:11434/v1"),
        ("lmstudio", ""),
        ("lm-studio", ""),
        ("local", ""),
        ("vllm", "http://127.0.0.1:8000/v1"),
        ("custom", "http://localhost:11434/v1"),
        ("custom", "http://127.0.0.1:8080/v1"),
        ("", "http://0.0.0.0:11434/v1"),
    ],
)
def test_local_endpoints_detected(provider, base_url):
    assert _model_is_local_endpoint(provider, base_url) is True


@pytest.mark.parametrize(
    "provider,base_url",
    [
        ("openrouter", "https://openrouter.ai/api/v1"),
        ("openai", ""),
        ("anthropic", "https://api.anthropic.com"),
        ("deepseek", "https://api.deepseek.com"),
        # A remote/LAN "custom" endpoint is NOT treated as local (conservative):
        # only named-local providers or loopback hosts relax the guard.
        ("custom", "http://192.168.0.103:11434/v1"),
    ],
)
def test_cloud_and_remote_not_local(provider, base_url):
    assert _model_is_local_endpoint(provider, base_url) is False


def test_handles_none_inputs():
    assert _model_is_local_endpoint(None, None) is False
