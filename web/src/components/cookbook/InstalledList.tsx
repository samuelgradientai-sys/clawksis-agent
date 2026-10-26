import { useState } from "react";
import { Check, Pencil, ShieldCheck, Trash2 } from "lucide-react";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { fmtBytes, type InstalledModel } from "@/lib/cookbook";
import { CbButton, Pill, Row } from "./CookbookUi";

interface InstalledActions {
  busyModel: string | null;
  onUse: (m: InstalledModel) => void;
  onVerify: (m: InstalledModel) => void;
  onRename: (m: InstalledModel, name: string) => void;
  onDelete: (m: InstalledModel) => void;
}

function InstalledRow({ model: m, actions, onAskDelete }: { model: InstalledModel; actions: InstalledActions; onAskDelete: () => void }) {
  const [renaming, setRenaming] = useState<string | null>(null);
  const busy = actions.busyModel === m.id;
  const gguf = m.provider === "llamacpp";
  const submit = () => {
    const name = renaming?.trim();
    setRenaming(null);
    if (name && name !== m.name) actions.onRename(m, name);
  };
  return (
    <Row className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <Pill kind={gguf ? "llamacpp" : "ollama"}>{gguf ? "llama.cpp" : "Ollama"}</Pill>
          {renaming !== null ? (
            <input
              autoFocus
              value={renaming}
              aria-label={`New name for ${m.name}`}
              onChange={(e) => setRenaming(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
                if (e.key === "Escape") setRenaming(null);
              }}
              className="h-7 min-w-0 flex-1 rounded-lg border border-[rgb(var(--clawk-liquid-violet)/0.5)] bg-black/20 px-2 text-sm outline-none sm:max-w-xs"
            />
          ) : (
            <span className="min-w-0 break-all font-medium">{m.name}</span>
          )}
          {m.quant && <Pill>{m.quant}</Pill>}
        </div>
        <p className="mt-1 truncate text-xs text-muted-foreground" title={m.path || m.repo}>
          {fmtBytes(m.size_bytes)}
          {m.repo ? ` · ${m.repo}` : ""}
          {m.path ? ` · ${m.path}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
        <CbButton tone="primary" disabled={busy} onClick={() => actions.onUse(m)}>
          {busy ? "Working…" : "Use"}
        </CbButton>
        {gguf && renaming !== null && (
          <CbButton onClick={submit} aria-label="Save name">
            <Check className="h-3.5 w-3.5" />
          </CbButton>
        )}
        {gguf && renaming === null && (
          <>
            <CbButton tone="ghost" disabled={busy} onClick={() => actions.onVerify(m)} title="Check file integrity (size + GGUF magic)" aria-label={`Verify ${m.name}`}>
              <ShieldCheck className="h-3.5 w-3.5" />
            </CbButton>
            <CbButton tone="ghost" onClick={() => setRenaming(m.name)} aria-label={`Rename ${m.name}`} title="Rename">
              <Pencil className="h-3.5 w-3.5" />
            </CbButton>
          </>
        )}
        <CbButton tone="ghost" disabled={busy} onClick={onAskDelete} aria-label={`Delete ${m.name}`} title="Delete" className="hover:text-rose-300">
          <Trash2 className="h-3.5 w-3.5" />
        </CbButton>
      </div>
    </Row>
  );
}

/** Installed models across backends: use, verify, rename, delete (confirmed). */
export function InstalledList({
  models,
  loading,
  actions,
}: {
  models: InstalledModel[];
  loading: boolean;
  actions: InstalledActions;
}) {
  const [pending, setPending] = useState<InstalledModel | null>(null);
  if (loading && models.length === 0) return <p className="text-sm text-muted-foreground">Loading installed models…</p>;
  return (
    <div className="grid gap-2">
      {models.length === 0 && (
        <Row className="border-dashed text-sm text-muted-foreground">
          No local models yet. Find one in the Models tab — Ollama downloads it, or pick a GGUF version for llama.cpp.
        </Row>
      )}
      {models.map((m) => (
        <InstalledRow key={`${m.provider}:${m.id}`} model={m} actions={actions} onAskDelete={() => setPending(m)} />
      ))}
      <DeleteConfirmDialog
        open={pending !== null}
        onCancel={() => setPending(null)}
        onConfirm={() => {
          if (pending) actions.onDelete(pending);
          setPending(null);
        }}
        title={pending ? `Delete ${pending.name}?` : "Delete model?"}
        description="The model file is removed from disk. Download it again to use it."
        loading={false}
      />
    </div>
  );
}
