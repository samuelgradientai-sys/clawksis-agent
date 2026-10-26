// Ollama provider status for the Cookbook page.

export interface OllamaCardStatus {
  installed?: boolean;
  running?: boolean;
  models?: string[];
}

/** Ollama is usable when its daemon answers, binary on our PATH or not (a container, a service
 *  account or OLLAMA_HOST on another box) — pulls and "use" go over its HTTP API. */
export function ollamaAvailable(ollama: OllamaCardStatus): boolean {
  return Boolean(ollama.installed || ollama.running);
}

export function ollamaStatusText(ollama: OllamaCardStatus, install: string): string {
  if (ollama.running) {
    const where = ollama.installed ? "" : " (external daemon)";
    return `Running${where} · ${String(ollama.models?.length ?? 0)} model(s) pulled`;
  }
  if (ollama.installed) return "Installed — starts automatically when you pull a model.";
  if (install.startsWith("error")) return install;
  return install === "installing" ? "Installing on this machine…" : "Not installed.";
}
