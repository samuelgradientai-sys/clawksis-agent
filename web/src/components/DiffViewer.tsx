import { useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  FileDiff,
} from "lucide-react";
import Prism from "prismjs";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-jsx";
import "prismjs/components/prism-tsx";
import "prismjs/components/prism-python";
import "prismjs/components/prism-json";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-markdown";
import "./diff-prism.css";

/**
 * Git-style side-by-side diff viewer for the agent's file edits (Claude Code /
 * GitHub PR look). Parses the raw unified-diff the backend already produces
 * (`PatchResult.diff` via Python `difflib`, surfaced as `tool.inline_diff`):
 *
 *  - per-file sections with a +adds/−dels summary, collapsible;
 *  - aligned old|new columns with line numbers, red (removed) / green (added);
 *  - Prism syntax highlighting (language inferred from the file extension);
 *  - a toolbar to collapse/expand all files and jump between files.
 *
 * Falls back to a plain colorized block when the string isn't a unified diff.
 */

type LineKind = "context" | "del" | "add";

interface DiffLine {
  kind: LineKind;
  oldN?: number;
  newN?: number;
  text: string;
}

interface Hunk {
  heading: string;
  lines: DiffLine[];
}

interface FileDiff {
  path: string;
  hunks: Hunk[];
  adds: number;
  dels: number;
}

/** Strip the `a/`|`b/` prefix and any trailing tab-metadata from a diff path. */
function cleanPath(raw: string): string {
  return (
    raw
      .replace(/^[ab]\//, "")
      .replace(/\t.*$/, "")
      .trim() || "(archivo)"
  );
}

export function parseUnifiedDiff(diff: string): FileDiff[] {
  const files: FileDiff[] = [];
  let cur: FileDiff | null = null;
  let hunk: Hunk | null = null;
  let oldN = 0;
  let newN = 0;

  const startFile = (path: string): FileDiff => {
    const next: FileDiff = { path, hunks: [], adds: 0, dels: 0 };
    files.push(next);
    hunk = null;
    cur = next;
    return next;
  };

  for (const raw of diff.split("\n")) {
    if (raw.startsWith("diff --git")) {
      cur = startFile("");
      continue;
    }
    if (raw.startsWith("--- ")) {
      if (!cur || cur.hunks.length > 0) cur = startFile("");
      continue;
    }
    if (raw.startsWith("+++ ")) {
      if (!cur) cur = startFile("");
      if (cur) cur.path = cleanPath(raw.slice(4));
      continue;
    }
    const m = raw.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$/);
    if (m) {
      if (!cur) cur = startFile("");
      oldN = parseInt(m[1], 10);
      newN = parseInt(m[2], 10);
      hunk = { heading: m[3].trim(), lines: [] };
      cur!.hunks.push(hunk);
      continue;
    }
    if (!hunk || !cur) continue;

    if (raw.startsWith("-")) {
      hunk.lines.push({ kind: "del", oldN, text: raw.slice(1) });
      oldN++;
      cur.dels++;
    } else if (raw.startsWith("+")) {
      hunk.lines.push({ kind: "add", newN, text: raw.slice(1) });
      newN++;
      cur.adds++;
    } else if (raw.startsWith("\\")) {
      // "\ No newline at end of file" — metadata, skip.
    } else {
      const text = raw.startsWith(" ") ? raw.slice(1) : raw;
      hunk.lines.push({ kind: "context", oldN, newN, text });
      oldN++;
      newN++;
    }
  }

  return files;
}

interface Row {
  left?: DiffLine;
  right?: DiffLine;
  context: boolean;
}

/** Align a hunk's lines into side-by-side rows: paired del↔add, context spans both. */
function alignHunk(lines: DiffLine[]): Row[] {
  const rows: Row[] = [];
  let dels: DiffLine[] = [];
  let adds: DiffLine[] = [];

  const flush = () => {
    const n = Math.max(dels.length, adds.length);
    for (let i = 0; i < n; i++) {
      rows.push({ left: dels[i], right: adds[i], context: false });
    }
    dels = [];
    adds = [];
  };

  for (const ln of lines) {
    if (ln.kind === "del") dels.push(ln);
    else if (ln.kind === "add") adds.push(ln);
    else {
      flush();
      rows.push({ left: ln, right: ln, context: true });
    }
  }
  flush();
  return rows;
}

// ── Syntax highlighting (Prism) ───────────────────────────────────────────

const EXT_LANG: Record<string, string> = {
  ts: "typescript",
  tsx: "tsx",
  js: "javascript",
  jsx: "jsx",
  mjs: "javascript",
  cjs: "javascript",
  py: "python",
  json: "json",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  yml: "yaml",
  yaml: "yaml",
  md: "markdown",
  markdown: "markdown",
  css: "css",
  scss: "css",
  html: "markup",
  xml: "markup",
  svg: "markup",
};

function langForPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return EXT_LANG[ext] ?? "";
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Prism-highlighted HTML for one line, or escaped text when no grammar. */
function highlightLine(text: string, lang: string): string {
  const grammar = lang ? Prism.languages[lang] : undefined;
  if (!grammar) return escapeHtml(text);
  try {
    return Prism.highlight(text, grammar, lang);
  } catch {
    return escapeHtml(text);
  }
}

function Num({ n }: { n?: number }) {
  return (
    <td className="select-none border-r border-border/40 px-1.5 text-right align-top tabular-nums text-text-tertiary">
      {n ?? ""}
    </td>
  );
}

function Cell({
  line,
  side,
  lang,
}: {
  line?: DiffLine;
  side: "left" | "right";
  lang: string;
}) {
  if (!line) return <td className="bg-muted/10" />;
  const isChange = line.kind !== "context";
  const tone = !isChange
    ? ""
    : side === "left"
      ? "bg-destructive/10"
      : "bg-success/10";
  const sign = !isChange ? " " : side === "left" ? "-" : "+";
  return (
    <td className={"whitespace-pre px-1.5 align-top " + tone}>
      <span className="select-none opacity-40">{sign}</span>
      <span
        dangerouslySetInnerHTML={{ __html: highlightLine(line.text || " ", lang) }}
      />
    </td>
  );
}

function HunkRows({ heading, rows, lang }: { heading: string; rows: Row[]; lang: string }) {
  return (
    <>
      <tr className="bg-primary/5">
        <td
          colSpan={4}
          className="select-none px-2 py-0.5 text-[0.65rem] text-primary/80"
        >
          {"⋯ " + (heading || "cambios")}
        </td>
      </tr>
      {rows.map((r, i) => (
        <tr key={i} className={r.context ? "" : "bg-foreground/[0.015]"}>
          <Num n={r.left?.oldN} />
          <Cell line={r.left} side="left" lang={lang} />
          <Num n={r.right?.newN} />
          <Cell line={r.right} side="right" lang={lang} />
        </tr>
      ))}
    </>
  );
}

function FileBlock({
  file,
  open,
  onToggle,
}: {
  file: FileDiff;
  open: boolean;
  onToggle: () => void;
}) {
  const Chevron = open ? ChevronDown : ChevronRight;
  const lang = useMemo(() => langForPath(file.path), [file.path]);
  const rowsPerHunk = useMemo(
    () => file.hunks.map((h) => alignHunk(h.lines)),
    [file],
  );

  return (
    <div className="overflow-hidden rounded-md border border-border">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-1.5 bg-muted/40 px-2 py-1 text-left text-[0.7rem]"
      >
        <Chevron className="size-3 shrink-0 text-muted-foreground" />
        <FileDiff className="size-3 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate font-mono font-medium text-foreground">
          {file.path}
        </span>
        {file.adds > 0 && (
          <span className="shrink-0 font-mono text-success">+{file.adds}</span>
        )}
        {file.dels > 0 && (
          <span className="shrink-0 font-mono text-destructive">−{file.dels}</span>
        )}
      </button>

      {open && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse font-mono text-[0.7rem] leading-snug">
            <tbody>
              {file.hunks.map((h, hi) => (
                <HunkRows
                  key={hi}
                  heading={h.heading}
                  rows={rowsPerHunk[hi]}
                  lang={lang}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function DiffViewer({ diff }: { diff: string }) {
  const files = useMemo(() => parseUnifiedDiff(diff), [diff]);
  const [open, setOpen] = useState<boolean[]>(() => files.map(() => true));
  const fileRefs = useRef<(HTMLDivElement | null)[]>([]);
  const focused = useRef(0);

  const totals = useMemo(
    () =>
      files.reduce(
        (acc, f) => ({ adds: acc.adds + f.adds, dels: acc.dels + f.dels }),
        { adds: 0, dels: 0 },
      ),
    [files],
  );

  // Parsing produced nothing usable — fall back to a plain colorized block.
  if (files.length === 0 || files.every((f) => f.hunks.length === 0)) {
    return (
      <pre className="overflow-x-auto whitespace-pre text-[0.7rem] leading-snug">
        {diff.split("\n").map((line, i) => (
          <div
            key={i}
            className={
              line.startsWith("+") && !line.startsWith("+++")
                ? "text-success"
                : line.startsWith("-") && !line.startsWith("---")
                  ? "text-destructive"
                  : line.startsWith("@@")
                    ? "text-primary"
                    : "text-text-secondary"
            }
          >
            {line || " "}
          </div>
        ))}
      </pre>
    );
  }

  const allOpen = open.every(Boolean);
  const toggleAll = () => setOpen(files.map(() => !allOpen));
  const toggleOne = (i: number) =>
    setOpen((prev) => prev.map((v, j) => (j === i ? !v : v)));

  const jump = (dir: 1 | -1) => {
    const n = files.length;
    const idx = ((focused.current + dir) % n + n) % n;
    focused.current = idx;
    fileRefs.current[idx]?.scrollIntoView({ block: "center", behavior: "smooth" });
  };

  return (
    <div className="clawk-diff flex flex-col gap-1.5">
      <div className="flex items-center gap-2 text-[0.7rem] text-text-tertiary">
        <span>
          {files.length} {files.length === 1 ? "archivo" : "archivos"}
        </span>
        {totals.adds > 0 && <span className="text-success">+{totals.adds}</span>}
        {totals.dels > 0 && (
          <span className="text-destructive">−{totals.dels}</span>
        )}
        <span className="ml-auto flex items-center gap-1">
          {files.length > 1 && (
            <>
              <button
                type="button"
                onClick={() => jump(-1)}
                title="Cambio anterior"
                className="rounded p-0.5 hover:bg-muted hover:text-foreground"
              >
                <ChevronUpIcon />
              </button>
              <button
                type="button"
                onClick={() => jump(1)}
                title="Siguiente cambio"
                className="rounded p-0.5 hover:bg-muted hover:text-foreground"
              >
                <ChevronDownIcon />
              </button>
            </>
          )}
          <button
            type="button"
            onClick={toggleAll}
            title={allOpen ? "Colapsar todo" : "Expandir todo"}
            className="rounded p-0.5 hover:bg-muted hover:text-foreground"
          >
            {allOpen ? (
              <ChevronsDownUp className="size-3.5" />
            ) : (
              <ChevronsUpDown className="size-3.5" />
            )}
          </button>
        </span>
      </div>
      {files.map((f, i) => (
        <div
          key={i}
          ref={(el) => {
            fileRefs.current[i] = el;
          }}
        >
          <FileBlock file={f} open={open[i] ?? true} onToggle={() => toggleOne(i)} />
        </div>
      ))}
    </div>
  );
}

function ChevronUpIcon() {
  return <ChevronRight className="size-3.5 -rotate-90" />;
}
function ChevronDownIcon() {
  return <ChevronRight className="size-3.5 rotate-90" />;
}
