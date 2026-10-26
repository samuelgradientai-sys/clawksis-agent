import { ollamaAvailable, ollamaStatusText, type OllamaCardStatus } from "@/lib/cookbook-ollama";

/** The Ollama provider card: status, plus Install while no daemon is reachable. */
export function OllamaCard({
  ollama,
  install,
  onInstall,
}: {
  ollama: OllamaCardStatus;
  install: string;
  onInstall: () => void;
}) {
  const showInstall = !ollamaAvailable(ollama) && install !== "done";
  return (
    <div className="rounded-lg border border-border bg-card/40 p-3 text-sm">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-medium">Ollama</span>
        {showInstall &&
          (install === "installing" ? (
            <span className="text-xs text-muted-foreground">installing…</span>
          ) : (
            <button
              type="button"
              onClick={onInstall}
              className="rounded-md border border-[var(--color-primary)] bg-[var(--color-primary)]/15 px-2 py-0.5 text-xs"
            >
              Install
            </button>
          ))}
      </div>
      <div className="text-muted-foreground">{ollamaStatusText(ollama, install)}</div>
    </div>
  );
}
