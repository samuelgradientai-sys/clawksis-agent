"""A4 (Hermes→Clawksis quick wins): agent-loop hardening.

Covers the universal parallel-tool-call guidance, stale-prompt detection after a
model/provider switch, and the generic observability event_callback.
"""

from agent import prompt_builder as pb
from agent.agent_init import emit_agent_event
from agent.conversation_loop import _stored_prompt_matches_runtime


class _FakeAgent:
    pass


class TestParallelToolCallGuidance:
    def test_block_exists_and_is_universal(self):
        assert hasattr(pb, "PARALLEL_TOOL_CALL_GUIDANCE")
        assert "Parallel tool calls" in pb.PARALLEL_TOOL_CALL_GUIDANCE
        assert "batch" in pb.PARALLEL_TOOL_CALL_GUIDANCE.lower()

    def test_google_block_no_longer_duplicates_steer(self):
        # The steer moved to the universal block; Gemini must not get it twice.
        assert "Parallel tool calls:" not in pb.GOOGLE_MODEL_OPERATIONAL_GUIDANCE


class TestEmitAgentEvent:
    def test_fires_callback(self):
        calls = []
        agent = _FakeAgent()
        agent.event_callback = lambda name, payload: calls.append((name, payload))
        emit_agent_event(agent, "memory_synced", {"n": 1})
        assert calls == [("memory_synced", {"n": 1})]

    def test_noop_without_callback(self):
        agent = _FakeAgent()
        agent.event_callback = None
        emit_agent_event(agent, "x", {})  # must not raise

    def test_missing_attr_is_safe(self):
        emit_agent_event(_FakeAgent(), "x", {})  # no event_callback attr at all

    def test_listener_exception_swallowed(self):
        def _boom(name, payload):
            raise RuntimeError("listener blew up")

        agent = _FakeAgent()
        agent.event_callback = _boom
        emit_agent_event(agent, "x", {"a": 1})  # must not propagate

    def test_none_payload_becomes_empty_dict(self):
        seen = []
        agent = _FakeAgent()
        agent.event_callback = lambda name, payload: seen.append(payload)
        emit_agent_event(agent, "x", None)
        assert seen == [{}]


class TestStoredPromptMatchesRuntime:
    def _agent(self, model, provider):
        a = _FakeAgent()
        a.model = model
        a.provider = provider
        return a

    def test_same_identity_matches(self):
        a = self._agent("deepseek-chat", "deepseek")
        assert _stored_prompt_matches_runtime(
            a, "Model: deepseek-chat\nProvider: deepseek"
        ) is True

    def test_model_drift_rejected(self):
        a = self._agent("deepseek-chat", "deepseek")
        assert _stored_prompt_matches_runtime(
            a, "Model: gpt-4o\nProvider: deepseek"
        ) is False

    def test_provider_drift_rejected(self):
        a = self._agent("deepseek-chat", "deepseek")
        assert _stored_prompt_matches_runtime(
            a, "Model: deepseek-chat\nProvider: openrouter"
        ) is False

    def test_no_identity_lines_passthrough(self):
        a = self._agent("deepseek-chat", "deepseek")
        assert _stored_prompt_matches_runtime(a, "no identity here") is True
