"""``codex_exec`` — delegate a coding task to OpenAI's Codex CLI.

Runs the ``codex`` CLI non-interactively via ``codex exec``. The tool only
appears to the model when ``codex`` is installed (``check_fn``); the toolset is
off by default and enabled in ``clawk tools`` → Codex CLI.

Reference: https://github.com/openai/codex
"""

from tools.coding_cli_common import cli_available, resolve_cli, run_coding_cli
from tools.registry import registry, tool_result

CODEX_SCHEMA = {
    "name": "codex_exec",
    "description": (
        "Delegate a software-engineering task to OpenAI's Codex coding agent "
        "(the `codex` CLI). Codex works autonomously in a project directory: "
        "it reads and edits files and runs commands to complete the task, then "
        "returns a summary. Give it a complete, self-contained task description "
        "(implement a feature, fix a bug, refactor, add tests). Requires the "
        "`codex` CLI installed and authenticated (OPENAI_API_KEY or ChatGPT "
        "login). Non-interactive — it will not ask follow-up questions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The full task / instructions for Codex.",
            },
            "workdir": {
                "type": "string",
                "description": (
                    "Absolute path to the project directory Codex should work "
                    "in. Defaults to the current session working directory."
                ),
            },
            "model": {
                "type": "string",
                "description": (
                    "Optional model override (e.g. 'gpt-5-codex'). Omit to use "
                    "Codex's configured default."
                ),
            },
            "yolo": {
                "type": "boolean",
                "description": (
                    "When false (default), Codex runs sandboxed with "
                    "workspace-write auto-approval — edits stay confined to the "
                    "workspace and no prompts block the run. When true, runs "
                    "with --dangerously-bypass-approvals-and-sandbox (full disk "
                    "+ network access, no sandbox). Only set true in an already "
                    "isolated/disposable environment."
                ),
                "default": False,
            },
            "json": {
                "type": "boolean",
                "description": (
                    "Emit Codex's structured JSONL event stream instead of "
                    "plain-text output."
                ),
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


def _handle_codex(args, **kw):
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return tool_result(ok=False, cli="codex", error="`prompt` is required.")

    cli = resolve_cli("codex")
    if not cli:
        return tool_result(
            ok=False,
            cli="codex",
            error="`codex` CLI not installed. Install with: npm install -g @openai/codex",
        )

    argv = [cli, "exec"]
    if args.get("yolo"):
        argv.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        argv += ["--sandbox", "workspace-write"]
    if args.get("json"):
        argv.append("--json")
    model = (args.get("model") or "").strip()
    if model:
        argv += ["-m", model]
    # The parent agent's workdir may not be a git repo; don't let that block us.
    argv.append("--skip-git-repo-check")
    argv.append(prompt)

    return run_coding_cli(
        cli_label="codex",
        argv=argv,
        workdir=args.get("workdir"),
        timeout=args.get("timeout"),
        prompt=prompt,
    )


registry.register(
    name="codex_exec",
    toolset="codex_cli",
    schema=CODEX_SCHEMA,
    handler=_handle_codex,
    check_fn=lambda: cli_available("codex"),
    emoji="🤖",
    max_result_size_chars=60_000,
)
