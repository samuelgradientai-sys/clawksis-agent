import { Cpu, HardDrive, Server } from "lucide-react";
import { ollamaAvailable, ollamaStatusText } from "@/lib/cookbook-ollama";
import type { Hardware, LlamaCppStatus, OllamaStatus } from "@/lib/cookbook";
import { CbButton, Panel, Pill } from "./CookbookUi";

function CardTitle({ icon: Icon, title, state }: { icon: typeof Cpu; title: string; state?: React.ReactNode }) {
  return (
    <div className="mb-1.5 flex min-w-0 items-center justify-between gap-2 sm:mb-2">
      <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
        <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="truncate">{title}</span>
      </span>
      {state}
    </div>
  );
}

export function HardwareCard({ hw }: { hw: Hardware }) {
  const gpu = hw.gpu_name ? `${hw.gpu_name} · ${hw.vram_gb ?? 0} GB VRAM` : "No discrete GPU (CPU inference)";
  return (
    <Panel>
      <CardTitle icon={Cpu} title="This machine" state={hw.platform ? <Pill>{hw.platform}</Pill> : undefined} />
      <div className="text-sm">
        <span className="text-xl font-semibold tabular-nums sm:text-2xl">{hw.ram_gb ?? "?"}</span>
        <span className="ml-1 text-muted-foreground">GB RAM</span>
        {hw.ram_available_gb ? (
          <span className="ml-2 text-xs text-muted-foreground">{hw.ram_available_gb} GB free</span>
        ) : null}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">
        {hw.cpu_cores ?? "?"} cores · {gpu}
      </div>
      <div className="mt-0.5 text-xs text-muted-foreground">
        {hw.disk_free_gb ? `${hw.disk_free_gb} GB disk free for models` : ""}
        {hw.load_1m ? ` · load ${hw.load_1m}` : ""}
      </div>
    </Panel>
  );
}

function InstallControl({ install, onInstall }: { install: string; onInstall: () => void }) {
  if (install === "done") return <Pill kind="ok">installed</Pill>;
  if (install === "installing") return <Pill kind="info">installing…</Pill>;
  return (
    <CbButton tone="primary" className="px-2.5 py-1" onClick={onInstall}>
      Install
    </CbButton>
  );
}

/** Ollama: status, plus Install while no daemon is reachable (a container's daemon counts). */
export function OllamaCard({
  ollama,
  install,
  onInstall,
}: {
  ollama: OllamaStatus;
  install: string;
  onInstall: () => void;
}) {
  const ready = ollamaAvailable(ollama);
  return (
    <Panel>
      <CardTitle
        icon={Server}
        title="Ollama"
        state={ready ? <Pill kind="ok">{ollama.running ? "running" : "installed"}</Pill> : <InstallControl install={install} onInstall={onInstall} />}
      />
      <p className={`text-xs ${install.startsWith("error") && !ready ? "text-rose-300" : "text-muted-foreground"}`}>
        {ollamaStatusText(ollama, install)}
      </p>
    </Panel>
  );
}

function llamaStatusText(llamacpp: LlamaCppStatus, install: string): string {
  const count = String(llamacpp.models?.length ?? 0);
  if (llamacpp.installed) {
    return llamacpp.server?.running
      ? `Serving ${llamacpp.server.model_file || "a model"} · ${count} GGUF installed`
      : `Installed · ${count} GGUF model(s)`;
  }
  if (install.startsWith("error")) return `Install failed — ${install.replace(/^error:\s*/, "")}`;
  if (install === "installing") return "Downloading the prebuilt llama.cpp release…";
  return "Not installed. Runs GGUF models from Hugging Face.";
}

export function LlamaCppCard({
  llamacpp,
  install,
  stopping,
  onInstall,
  onStop,
}: {
  llamacpp: LlamaCppStatus;
  install: string;
  stopping: boolean;
  onInstall: () => void;
  onStop: () => void;
}) {
  const ready = llamacpp.installed || install === "done";
  const running = !!llamacpp.server?.running;
  return (
    <Panel>
      <CardTitle
        icon={HardDrive}
        title="llama.cpp"
        state={
          ready ? (
            <Pill kind={running ? "ok" : "muted"}>{running ? "serving" : "installed"}</Pill>
          ) : (
            <InstallControl install={install} onInstall={onInstall} />
          )
        }
      />
      <p className={`text-xs ${install.startsWith("error") && !ready ? "text-rose-300" : "text-muted-foreground"}`}>
        {llamaStatusText(llamacpp, install)}
      </p>
      {running && (
        <CbButton tone="danger" className="mt-2 px-2.5 py-1" disabled={stopping} onClick={onStop}>
          {stopping ? "Stopping…" : "Stop server (free RAM)"}
        </CbButton>
      )}
    </Panel>
  );
}
