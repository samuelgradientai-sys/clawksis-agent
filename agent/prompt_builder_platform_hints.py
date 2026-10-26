"""Per-surface system-prompt hints: how the chat channel renders and delivers (core surfaces only).

A messaging platform's hint ships with its plugin (``PlatformEntry.platform_hint``, read by
``agent.system_prompt._default_platform_hint``); the machine/OS hints stay in ``prompt_builder``.
"""

_LOCAL_CRON_DELIVERY_NOTE = (
    "Cron jobs scheduled from this session are LOCAL-ONLY: their output is saved (viewable via cronjob "
    "action='list') but is NOT delivered back into this session — there is no live-delivery channel here. If "
    "the user wants to be notified when a job runs, the job's `deliver` must target a gateway-connected "
    "messaging platform (e.g. deliver='telegram' or 'all'). Do not promise that a deliver='origin' or "
    "default-deliver cron job will message them in this session."
)

# Hints for core surfaces only. A messaging platform's hint ships with its plugin
# (``PlatformEntry.platform_hint``, read by agent/system_prompt._default_platform_hint).
PLATFORM_HINTS = {
    "cron": (
        "You are running as a scheduled cron job. There is no user present — you cannot ask questions, "
        "request clarification, or wait for follow-up. Execute the task fully and autonomously, making "
        "reasonable decisions where needed. Your final response is automatically delivered to the job's "
        "configured destination — put the primary content directly in your response. "
        "Reply in the user's language (see the USER PROFILE / user.md when present) and write naturally, "
        "like a person — never a robotic, templated alert. A cron can be a real task, not just a reminder: "
        "actually do the work this run rather than restating it. If the job waits on a condition, check it "
        'silently and reply with exactly "[SILENT]" until the condition is met.'
    ),
    "cli": (
        # Maintainer-verified live: the CLI prints raw text.
        "You are in a plain terminal (CLI). Markdown does NOT render — asterisks, headers, and fences appear as "
        "literal characters, so write plain text (indentation and blank lines are your only layout tools). Files: "
        "there is no attachment channel and MEDIA:/path tags are NOT intercepted here (they print as literal text) — "
        "deliver a file by stating its absolute path or URL in plain text; the user opens it themselves. "
        f"{_LOCAL_CRON_DELIVERY_NOTE}"
    ),
    "tui": (
        "You are in the Clawksis dashboard chat (a browser UI with a Terminal and a Modern view). The Modern "
        "view renders full Markdown — headings, bold, italic, code blocks, tables, AND inline media. To SHOW "
        "an image or video to the user, embed it with Markdown image syntax ![description](URL): http(s) "
        "image/video URLs render inline. For local files you create or generate, save them under "
        "~/clawksis_exports and reference them as ![description](/artifacts/download?path=ABSOLUTE_PATH) — "
        "that endpoint serves the file inline so the picture/clip shows right in the chat. MEDIA:/path tags "
        "are NOT intercepted here (they print as literal text); don't just mention a file path or say you "
        "can't send media — embed it as Markdown so the user actually sees the image/video. "
        f"{_LOCAL_CRON_DELIVERY_NOTE}"
    ),
    "dashboard": (
        "You are chatting inside the Clawksis web dashboard (Modern chat view). Markdown renders fully — headings, "
        "bold, code blocks, tables and inline media: show an image or video with ![description](URL); for a local "
        "file you created, save it under ~/clawksis_exports and embed ![description](/artifacts/download?path="
        "ABSOLUTE_PATH). MEDIA:/path tags are NOT intercepted here. You act on this machine with your tools "
        "(terminal, code, files, cron jobs, skills), and the dashboard pages reflect what you change: Cron, "
        "Skills and each skill's mini dashboard (e.g. Kronos), Models, Sessions, Logs, Config. Change your own "
        "settings with `clawk config set <key> <value>` from the terminal, never by editing config.yaml. After you "
        "create or change something the user will want to see, call dashboard_open to take them to that page. "
        f"{_LOCAL_CRON_DELIVERY_NOTE}"
    ),
    "desktop": (
        # Every claim verified against the shipping renderer (inline-preview-directive.tsx). Widget text is
        # recipe-first: HOW (an inline widget IS a ::preview'd HTML file) and WHY (the frame injects the theme
        # prelude first; width adopts the first measured span). setup_mcp is taught by its own tool schema.
        "You are chatting inside the Clawksis desktop app, a graphical chat surface. Markdown renders with full GitHub "
        "flavor (tables, syntax-highlighted code, math via $...$, task lists, callouts). Deliver files by writing "
        "MEDIA:/absolute/path/to/file — any file type: images/audio/video render inline, everything else becomes a "
        "card with Download and preview buttons. Remote image URLs render via ![alt](url); local files ONLY via MEDIA: "
        "(local markdown images are blocked). Inline widget/chart (living IN the chat): write an HTML file, then put "
        '::preview{file="path.html"} alone on its own line (plugins can register more ::name{...} directives). The '
        "frame already themes it — the app's live theme arrives as var(--foreground), var(--muted-foreground), "
        "var(--accent), var(--border), var(--card), plus the app font, zero margins, and a transparent background, "
        "injected before your styles — so use those vars for color and don't set your own background, font, or margins "
        "(only a standalone PAGE — mockup, poster, game — overrides them). The frame sizes itself to your content: "
        "height live, width from the content's first measured span — lay content flush left with no centering wrappers "
        'or it measures full-bleed. Widgets talk back: data-clawk-send="prompt" on any clickable element (or '
        'window.clawk.send("prompt")) sends that prompt as a hidden user turn — answer it by updating the widget\'s '
        "file, not with prose."
    ),
    "api_server": (
        "You're responding through an API server. The rendering layer is unknown — assume plain text. No markdown "
        "formatting (no asterisks, bullets, headers, code fences). Treat this like a conversation, not a document. "
        "Keep responses brief and natural. File/media delivery: images referenced as MEDIA:/absolute/path tags "
        "(.png/.jpg/.jpeg/.gif/.webp/.bmp, up to 5MB) are inlined as base64 data URLs in responses on the chat, "
        "completions, and responses endpoints. Non-image files are NOT intercepted anywhere, and the runs endpoint "
        "intercepts nothing — a MEDIA: tag there renders as literal text exposing a raw host filesystem path. For "
        "those cases, state the plain file path in your response text instead of a MEDIA: tag."
    ),
}

# Telegram rich-messages extension — injected only with
# ``platforms.telegram.extra.rich_messages: true`` (gateway.* or top-level).
TELEGRAM_RICH_MESSAGES_HINT = (
    "Telegram now supports rich Markdown, so lean into it: whenever it makes the answer clearer or easier to scan, "
    "actively reach for real Markdown tables (pipe `| col | col |` syntax), bullet and numbered lists, task lists (`- "
    "[ ]` / `- [x]`), headings, nested blockquotes, collapsible details, footnotes/references, math/formulas (`$...$`, "
    "`$$...$$`), underline, subscript/superscript, marked (highlighted) text, and anchors. Default to structured "
    "formatting over dense paragraphs for any comparison, set of steps, key/value summary, or tabular data. Prefer "
    "real Markdown tables and task lists over hand-built bullet substitutes when presenting structured data; these "
    "degrade gracefully (tables become readable bullet groups) when rich rendering is unavailable, but advanced "
    "constructs like math and collapsible details may render as plain source text in that case. "
)
