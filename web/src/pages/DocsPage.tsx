import { useLayoutEffect } from "react";
import { ExternalLink } from "lucide-react";
import { Card, CardContent } from "@nous-research/ui/ui/components/card";
import { useI18n } from "@/i18n";
import { usePageHeader } from "@/contexts/usePageHeader";
import { cn } from "@/lib/utils";
import { PluginSlot } from "@/plugins";

export const CLAWK_DOCS_URL =
  "https://github.com/samuelgradientai-sys/clawksis-agent";

const DS_BUTTON_OUTLINED_LINK_CN = cn(
  "group relative inline-grid grid-cols-[auto_1fr_auto] items-center",
  "px-[.9em_.75em] py-[1.25em] gap-2",
  "leading-0 font-bold tracking-[0.2em] uppercase",
  "text-midground bg-transparent shadow-midground",
  "shadow-[inset_-1px_-1px_0_0_#00000080,inset_1px_1px_0_0_#ffffff80]",
);

// In-app quick reference. GitHub refuses to be embedded in an <iframe>
// (X-Frame-Options: DENY), so the previous framed docs view rendered blank.
// This page gives a usable local overview and links out to the full docs in
// a new tab instead.
const AREAS: { title: string; tab: string; blurb: string }[] = [
  {
    title: "Models & Providers",
    tab: "Models · Env",
    blurb:
      "Pick your main + auxiliary models, connect a provider (Claude, OpenAI, OpenRouter, DeepSeek, Gemini…) and manage API keys.",
  },
  {
    title: "Chat",
    tab: "Chat",
    blurb:
      "Talk to the agent in an embedded terminal, watch live tool-calls, switch model on the fly and resume past sessions.",
  },
  {
    title: "Skills & Plugins",
    tab: "Skills · Plugins",
    blurb:
      "Enable skills and toolsets, install from the hub, and manage agent / dashboard plugins (memory, browser, kanban…).",
  },
  {
    title: "Channels",
    tab: "Channels",
    blurb:
      "Connect WhatsApp, Telegram, Discord, Slack and more. Enter credentials, test the connection and restart the gateway.",
  },
  {
    title: "Proactivity — Cron & Webhooks",
    tab: "Cron · Webhooks",
    blurb:
      "Schedule recurring jobs (with model / skills / script overrides) and react to external events via signed webhooks.",
  },
  {
    title: "MCP",
    tab: "MCP",
    blurb:
      "Add Model Context Protocol servers (HTTP/SSE or stdio), or install them from the catalog to extend the agent's tools.",
  },
];

export default function DocsPage() {
  const { t } = useI18n();
  const { setEnd } = usePageHeader();

  useLayoutEffect(() => {
    setEnd(
      <a
        href={CLAWK_DOCS_URL}
        target="_blank"
        rel="noopener noreferrer"
        className={DS_BUTTON_OUTLINED_LINK_CN}
      >
        <ExternalLink className="size-3.5" />
        {t.app.openDocumentation}
      </a>,
    );
    return () => {
      setEnd(null);
    };
  }, [setEnd, t]);

  return (
    <div
      className={cn(
        "flex min-h-0 w-full min-w-0 flex-1 flex-col gap-6",
        "pt-1 sm:pt-2",
      )}
    >
      <PluginSlot name="docs:top" />

      <div className="flex flex-col gap-2">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Quick reference for the Clawksis dashboard. Each area below maps to a
          tab in the sidebar. For the full documentation, open the repository in
          a new tab.
        </p>
        <a
          href={CLAWK_DOCS_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 self-start text-sm text-primary hover:underline"
        >
          <ExternalLink className="h-4 w-4" />
          Open full documentation on GitHub
        </a>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {AREAS.map((a) => (
          <Card key={a.title} className="rounded-none">
            <CardContent className="flex flex-col gap-1.5 py-4">
              <span className="text-sm font-medium">{a.title}</span>
              <span className="text-xs uppercase tracking-wide text-muted-foreground">
                {a.tab}
              </span>
              <p className="text-xs leading-relaxed text-text-secondary">
                {a.blurb}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <PluginSlot name="docs:bottom" />
    </div>
  );
}
