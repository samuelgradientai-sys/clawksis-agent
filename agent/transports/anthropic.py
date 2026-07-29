"""Anthropic Messages API transport.



Delegates to the existing adapter functions in agent/anthropic_adapter.py.

This transport owns format conversion and normalization — NOT client lifecycle.

"""

from typing import Any, Dict, List, Optional


from agent.transports.base import ProviderTransport

from agent.transports.types import NormalizedResponse


class AnthropicTransport(ProviderTransport):
    """Transport for api_mode='anthropic_messages'.



    Wraps the existing functions in anthropic_adapter.py behind the

    ProviderTransport ABC.  Each method delegates — no logic is duplicated.

    """

    @property
    def api_mode(self) -> str:

        return "anthropic_messages"

    def convert_messages(self, messages: List[Dict[str, Any]], **kwargs) -> Any:
        """Convert OpenAI messages to Anthropic (system, messages) tuple.



        kwargs:

            base_url: Optional[str] — affects thinking signature handling.

        """

        from agent.anthropic_adapter import convert_messages_to_anthropic

        base_url = kwargs.get("base_url")

        return convert_messages_to_anthropic(messages, base_url=base_url)

    def convert_tools(self, tools: List[Dict[str, Any]]) -> Any:
        """Convert OpenAI tool schemas to Anthropic input_schema format."""

        from agent.anthropic_adapter import convert_tools_to_anthropic

        return convert_tools_to_anthropic(tools)

    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """Build Anthropic messages.create() kwargs.



        Calls convert_messages and convert_tools internally.



        params (all optional):

            max_tokens: int

            reasoning_config: dict | None

            tool_choice: str | None

            is_oauth: bool

            preserve_dots: bool

            context_length: int | None

            base_url: str | None

            fast_mode: bool

            drop_context_1m_beta: bool

        """

        from agent.anthropic_adapter import build_anthropic_kwargs

        return build_anthropic_kwargs(
            model=model,
            messages=messages,
            tools=tools,
            max_tokens=params.get("max_tokens", 16384),
            reasoning_config=params.get("reasoning_config"),
            tool_choice=params.get("tool_choice"),
            is_oauth=params.get("is_oauth", False),
            preserve_dots=params.get("preserve_dots", False),
            context_length=params.get("context_length"),
            base_url=params.get("base_url"),
            fast_mode=params.get("fast_mode", False),
            drop_context_1m_beta=params.get("drop_context_1m_beta", False),
        )

    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """Normalize Anthropic response to NormalizedResponse.



        Parses content blocks (text, thinking, tool_use), maps stop_reason

        to OpenAI finish_reason, and collects reasoning_details in provider_data.

        """

        import json

        from agent.anthropic_adapter import _to_plain_data, _sanitize_replay_block

        from agent.transports.types import ToolCall

        strip_tool_prefix = kwargs.get("strip_tool_prefix", False)

        _MCP_PREFIX = "mcp__"

        text_parts = []

        reasoning_parts = []

        reasoning_details = []

        tool_calls = []

        # Verbatim, order-preserving block list. Populated into provider_data
        # below only for turns that interleave SIGNED thinking with tool_use, so
        # replay (_convert_assistant_message) keeps the original ordering that
        # Anthropic signs thinking blocks against (else HTTP 400 on the latest
        # assistant message).
        ordered_blocks = []

        for block in response.content:
            block_dict = _to_plain_data(block)

            clean_block = None

            if isinstance(block_dict, dict):
                # Sanitize at capture so output-only SDK fields (parsed_output,

                # caller, citations=None, …) never persist to state.db and leak

                # back as request input on replay → HTTP 400 "Extra inputs are

                # not permitted". Defence-in-depth with the replay-side sanitize.

                clean_block = _sanitize_replay_block(block_dict)

                if clean_block is not None:
                    ordered_blocks.append(clean_block)

            if block.type == "text":
                text_parts.append(block.text)

            elif block.type in ("thinking", "redacted_thinking"):
                if block.type == "thinking":
                    reasoning_parts.append(block.thinking)

                # Use the sanitized block (clean_block) for reasoning_details too,

                # since _extract_preserved_thinking_blocks replays these on the

                # non-ordered path. Falls back to raw only if sanitize dropped it.

                if isinstance(clean_block, dict):
                    reasoning_details.append(clean_block)

                elif isinstance(block_dict, dict):
                    reasoning_details.append(block_dict)

            elif block.type == "tool_use":
                name = block.name

                if strip_tool_prefix and name.startswith(_MCP_PREFIX):
                    # On the OAuth wire every tool carries a double-underscore
                    # ``mcp__`` prefix (added in build_anthropic_kwargs to avoid
                    # Anthropic's single-underscore third-party classifier).
                    # Reverse it back to the name the registry/dispatcher knows.
                    # Two original forms map onto the same ``mcp__`` wire name:
                    #   ``mcp__read_file``       <- bare native tool ``read_file``
                    #   ``mcp__linear_get_issue`` <- MCP server tool
                    #                                ``mcp_linear_get_issue``
                    # Resolve by registry lookup, preferring whichever original
                    # is actually registered; never rewrite a name the LLM used
                    # that already resolves natively. GH-25255.
                    from tools.registry import registry as _tool_registry

                    if not _tool_registry.get_entry(name):
                        bare = name[len(_MCP_PREFIX) :]  # read_file
                        single = (
                            "mcp_" + bare
                        )  # mcp_read_file / mcp_linear_get_issue
                        if _tool_registry.get_entry(single):
                            name = single
                        elif _tool_registry.get_entry(bare):
                            name = bare

                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=name,
                        arguments=json.dumps(block.input),
                    )
                )

        finish_reason = self._STOP_REASON_MAP.get(response.stop_reason, "stop")

        provider_data = {}

        if reasoning_details:
            provider_data["reasoning_details"] = reasoning_details

        # Preserve interleave order for signed-thinking + tool_use turns so the
        # latest assistant message replays blocks in their original positions
        # (_convert_assistant_message reads this channel). The plain split into
        # reasoning_details + tool_calls loses the cross-type ordering, which
        # invalidates the thinking-block signatures on replay. Only worth
        # carrying when the turn actually interleaves the two shapes.
        _has_signed_thinking = any(
            isinstance(b, dict)
            and b.get("type") in ("thinking", "redacted_thinking")
            and (b.get("signature") or b.get("data"))
            for b in ordered_blocks
        )

        _has_tool_use = any(
            isinstance(b, dict) and b.get("type") == "tool_use"
            for b in ordered_blocks
        )

        if _has_signed_thinking and _has_tool_use:
            provider_data["anthropic_content_blocks"] = ordered_blocks

        return NormalizedResponse(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls or None,
            finish_reason=finish_reason,
            reasoning="\n\n".join(reasoning_parts) if reasoning_parts else None,
            usage=None,
            provider_data=provider_data or None,
        )

    def validate_response(self, response: Any) -> bool:
        """Check Anthropic response structure is valid.



        An empty content list is legitimate when ``stop_reason == "end_turn"``

        — the model's canonical way of signalling "nothing more to add" after

        a tool turn that already delivered the user-facing text. Treating it

        as invalid falsely retries a completed response.

        It is also legitimate when ``stop_reason == "refusal"`` (Claude 4.5+

        declines with an empty content list). Validating it lets the response

        flow through to normalize_response — which maps ``refusal`` to a

        ``content_filter`` finish reason — and the loop's refusal handler,

        instead of being rejected and retried as a deterministic refusal.

        """

        if response is None:
            return False

        content_blocks = getattr(response, "content", None)

        if not isinstance(content_blocks, list):
            return False

        if not content_blocks:
            return getattr(response, "stop_reason", None) in ("end_turn", "refusal")

        return True

    def extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]:
        """Extract Anthropic cache_read and cache_creation token counts."""

        usage = getattr(response, "usage", None)

        if usage is None:
            return None

        cached = getattr(usage, "cache_read_input_tokens", 0) or 0

        written = getattr(usage, "cache_creation_input_tokens", 0) or 0

        if cached or written:
            return {"cached_tokens": cached, "creation_tokens": written}

        return None

    # Promote the adapter's canonical mapping to module level so it's shared

    _STOP_REASON_MAP = {
        "end_turn": "stop",
        "tool_use": "tool_calls",
        "max_tokens": "length",
        "stop_sequence": "stop",
        "refusal": "content_filter",
        "model_context_window_exceeded": "length",
    }

    def map_finish_reason(self, raw_reason: str) -> str:
        """Map Anthropic stop_reason to OpenAI finish_reason."""

        return self._STOP_REASON_MAP.get(raw_reason, "stop")


# Auto-register on import

from agent.transports import register_transport  # noqa: E402


register_transport("anthropic_messages", AnthropicTransport)
