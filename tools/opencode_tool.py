"""``opencode_run`` — delegate a coding task to the OpenCode CLI.

Runs the open-source ``opencode`` CLI non-interactively via ``opencode run``.
The tool only appears to the model when ``opencode`` is installed
(``check_fn``); the toolset is off by default and enabled in
``clawk tools`` → OpenCode CLI.

Reference: https://github.com/sst/opencode
"""

from tools.coding_cli_common import cli_available, resolve_cli, run_coding_cli
from tools.registry import registry, tool_result

OPENCODE_SCHEMA = {
    "name": "opencode_run",
    "description": (
        "Delegate a software-engineering task to OpenCode, an open-source "
        "coding agent (the `opencode` CLI), running non-interactively via "
        "`opencode run`. OpenCode works autonomously in a project directory: "
        "reads and edits files, runs commands, and returns its result. Give it "
        "a complete, self-contained task description. OpenCode is provider-"
        "agnostic — it can use Anthropic, OpenAI, Google, OpenRouter, local "
        "models, etc. Requires the `opencode` CLI installed and a configured "
        "provider/API key (via `opencode auth login` or env keys)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The full task / instructions for OpenCode.",
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
                    "Optional model in 'provider/model' form (e.g. "
                    "'anthropic/claude-sonnet-4-5'). Omit to use OpenCode's "
                    "configured default."
                ),
            },
            "agent": {
                "type": "string",
                "description": "Optional named OpenCode agent profile to run as.",
            },
            "yolo": {
                "type": "boolean",
                "description": (
                    "When true, passes --dangerously-skip-permissions so "
                    "OpenCode auto-approves any permission not explicitly "
                    "denied (lets it edit/run without blocking). Only use in an "
                    "isolated/disposable environment. Default false."
                ),
                "default": False,
            },
            "json": {
                "type": "boolean",
                "description": "Emit OpenCode's raw JSON event output instead of plain text.",
                "default": False,
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


def _handle_opencode(args, **kw):
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return tool_result(ok=False, cli="opencode", error="`prompt` is required.")

    cli = resolve_cli("opencode")
    if not cli:
        return tool_result(
            ok=False,
            cli="opencode",
            error="`opencode` CLI not installed. Install with: npm install -g opencode-ai",
        )

    argv = [cli, "run"]
    if args.get("json"):
        argv += ["--format", "json"]
    model = (args.get("model") or "").strip()
    if model:
        argv += ["-m", model]
    agent = (args.get("agent") or "").strip()
    if agent:
        argv += ["--agent", agent]
    if args.get("yolo"):
        argv.append("--dangerously-skip-permissions")
    argv.append(prompt)

    return run_coding_cli(
        cli_label="opencode",
        argv=argv,
        workdir=args.get("workdir"),
        timeout=args.get("timeout"),
        prompt=prompt,
    )


registry.register(
    name="opencode_run",
    toolset="opencode_cli",
    schema=OPENCODE_SCHEMA,
    handler=_handle_opencode,
    check_fn=lambda: cli_available("opencode"),
    emoji="🟧",
    max_result_size_chars=60_000,
)
