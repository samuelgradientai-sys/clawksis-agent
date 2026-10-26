import { fmtCtx, isActivePull, TIER_STYLE, type CookbookModel, type TransferProgress } from "@/lib/cookbook";
import { CbButton, Pill, Row } from "./CookbookUi";
import { DownloadBar } from "./DownloadBar";

export function ToolsPill({ toolUse }: { toolUse: boolean }) {
  return toolUse ? (
    <Pill kind="ok" title="Supports function-calling: the agent can use tools">
      tools ✓
    </Pill>
  ) : (
    <Pill kind="warn" title="No function-calling: the agent fails the moment it calls a tool">
      no tools
    </Pill>
  );
}

function RowAction({
  model,
  status,
  ollamaReady,
  busy,
  onPull,
  onUse,
}: {
  model: CookbookModel;
  status: string;
  ollamaReady: boolean;
  busy: boolean;
  onPull: () => void;
  onUse: () => void;
}) {
  if (model.installed || status === "done") {
    return (
      <CbButton tone="primary" disabled={busy} onClick={onUse} title="Make this the agent's model for the selected profile">
        {busy ? "Switching…" : "Use"}
      </CbButton>
    );
  }
  if (isActivePull(status)) return <Pill kind="info">{status === "validating" ? "validating…" : "pulling…"}</Pill>;
  const fits = model.fit.tier !== "no_fit";
  const why = !ollamaReady ? "Install Ollama first" : !fits ? "Too big for this machine" : "Download with Ollama";
  return (
    <CbButton disabled={!fits || !ollamaReady} onClick={onPull} title={why}>
      Download
    </CbButton>
  );
}

/** One Ollama model (curated or library): fit verdict, what it brings, pull progress, action. */
export function ModelRow({
  model,
  pull,
  ollamaReady,
  busy,
  onPull,
  onCancel,
  onUse,
}: {
  model: CookbookModel;
  pull?: TransferProgress;
  ollamaReady: boolean;
  busy: boolean;
  onPull: () => void;
  onCancel: () => void;
  onUse: () => void;
}) {
  const tier = TIER_STYLE[model.fit.tier];
  const status = pull?.status ?? "";
  const error = status.startsWith("error") ? status.replace(/^error:\s*/, "") : null;
  return (
    <Row className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span className="font-medium">{model.name}</span>
          <span className="truncate font-mono text-xs text-muted-foreground">{model.ollama}</span>
          {model.installed && <Pill kind="ok">installed</Pill>}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <Pill className={tier.cls} title={model.fit.reason}>
            {tier.label}
          </Pill>
          <Pill kind="ollama">Ollama</Pill>
          <ToolsPill toolUse={model.tool_use} />
          {model.context > 0 && (
            <Pill kind="info" title={`Context window: ${model.context.toLocaleString()} tokens`}>
              ctx {fmtCtx(model.context)}
            </Pill>
          )}
          {model.size_gb > 0 && <span>~{model.size_gb} GB</span>}
          <span className="uppercase">{model.fit.mode}</span>
        </div>
        {model.use_case && <p className="mt-1 line-clamp-2 text-xs text-muted-foreground/80">{model.use_case}</p>}
        {status === "pulling" && pull && (
          <div className="mt-2 max-w-md">
            <DownloadBar label="Downloading" progress={pull} onCancel={onCancel} />
          </div>
        )}
        {error && <p className="mt-1 text-xs text-rose-300">{error}</p>}
      </div>
      <div className="flex shrink-0 justify-end">
        <RowAction model={model} status={status} ollamaReady={ollamaReady} busy={busy} onPull={onPull} onUse={onUse} />
      </div>
    </Row>
  );
}
