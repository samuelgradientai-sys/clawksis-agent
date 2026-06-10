"""``claude_code`` — delegate a coding task to Anthropic's Claude Code CLI.

Runs the ``claude`` CLI non-interactively via ``claude -p`` (print/headless
mode). The tool only appears to the model when ``claude`` is installed
(``check_fn``); the toolset is off by default and enabled in
``clawk tools`` → Claude Code CLI.

Reference: https://github.com/anthropics/claude-code
"""

from tools.coding_cli_common import cli_available, resolve_cli, run_coding_cli
from tools.registry import registry, tool_result

# Permission modes accepted by `claude --permission-mode`.
_PERMISSION_MODES = {"default", "acceptEdits", "plan", "bypassPermissions"}

CLAUDE_CODE_SCHEMA = {
    "name": "claude_code",
    "description": (
        "Delegate a software-engineering task to Anthropic's Claude Code agent "
        "(the `claude` CLI), running headless. Claude Code works autonomously "
        "in a project directory: reads and edits files, runs commands, and "
        "returns its result. Give it a complete, self-contained task "
        "description (implement a feature, fix a bug, refactor, write tests). "
        "Requires the `claude` CLI installed and authenticated (ANTHROPIC_API_"
        "KEY or a Claude subscription login). Non-interactive — it runs to "
        "completion without asking follow-ups."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The full task / instructions for Claude Code.",
            },
            "workdir": {
                "type": "string",
                "description": (
                    "Absolute path to the project directory to work in. "
                    "Defaults to the current session working directory."
                ),
            },
            "model": {
                "type": "string",
                "description": (
                    "Optional model override (e.g. 'claude-opus-4-8', "
                    "'sonnet'). Omit to use Claude Code's configured default."
                ),
            },
            "permission_mode": {
                "type": "string",
                "enum": sorted(_PERMISSION_MODES),
                "description": (
                    "Permission policy. 'acceptEdits' (default) auto-approves "
                    "file edits so the run doesn't block. 'plan' makes a plan "
                    "without changing anything. 'bypassPermissions' approves "
                    "everything including shell commands (use only when "
                    "isolated). 'default' may block on prompts — avoid headless."
                ),
                "default": "acceptEdits",
            },
            "yolo": {
                "type": "boolean",
                "description": (
                    "Shortcut for full autonomy: passes "
                    "--dangerously-skip-permissions (equivalent to "
                    "permission_mode=bypassPermissions). Overrides "
                    "permission_mode when true. Only use in an isolated/"
                    "disposable environment."
                ),
                "default": False,
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "json", "stream-json"],
                "description": "Output format from Claude Code. Default 'text'.",
                "default": "text",
            },
            "timeout": {
                "type": "integer",
                "description": "Max seconds before the run is killed (default 600, max 3600).",
                "minimum": 10,
            },
        },
        "required": ["prompt"],
    },
}


def _handle_claude_code(args, **kw):
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return tool_result(ok=False, cli="claude", error="`prompt` is required.")

    cli = resolve_cli("claude")
    if not cli:
        return tool_result(
            ok=False,
            cli="claude",
            error=(
                "`claude` CLI not installed. Install with: "
                "npm install -g @anthropic-ai/claude-code"
            ),
        )

    argv = [cli, "-p", prompt]

    output_format = (args.get("output_format") or "text").strip()
    if output_format in {"text", "json", "stream-json"}:
        argv += ["--output-format", output_format]

    if args.get("yolo"):
        argv.append("--dangerously-skip-permissions")
    else:
        mode = (args.get("permission_mode") or "acceptEdits").strip()
        if mode not in _PERMISSION_MODES:
            mode = "acceptEdits"
        if mode == "bypassPermissions":
            argv.append("--dangerously-skip-permissions")
        else:
            argv += ["--permission-mode", mode]

    model = (args.get("model") or "").strip()
    if model:
        argv += ["--model", model]

    return run_coding_cli(
        cli_label="claude",
        argv=argv,
        workdir=args.get("workdir"),
        timeout=args.get("timeout"),
        prompt=prompt,
    )


registry.register(
    name="claude_code",
    toolset="claude_code_cli",
    schema=CLAUDE_CODE_SCHEMA,
    handler=_handle_claude_code,
    check_fn=lambda: cli_available("claude"),
    emoji="🟣",
    max_result_size_chars=60_000,
)
