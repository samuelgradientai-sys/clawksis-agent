import type { ReactNode } from "react";
import { Search, X } from "lucide-react";
import type { CookbookFilters as Filters } from "@/lib/cookbook";
import { cn } from "@/lib/utils";

function Chip({ active, onClick, title, children }: { active: boolean; onClick: () => void; title?: string; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={cn(
        "shrink-0 rounded-full border px-2.5 py-1 text-xs transition-colors",
        active
          ? "clawk-liquid-chip border-[rgb(var(--clawk-liquid-violet)/0.5)] text-foreground"
          : "border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <span className="shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground/70">{label}</span>
      <div className="flex min-w-0 gap-1.5 overflow-x-auto">{children}</div>
    </div>
  );
}

/** Live search box + "browse all" and the characteristic filters (fit, tools, context, backend). */
export function CookbookSearchBar({
  query,
  onQuery,
  aside,
}: {
  query: string;
  onQuery: (q: string) => void;
  aside: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="relative min-w-0 flex-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          inputMode="search"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="Search Ollama + Hugging Face (qwen, llama, gemma…)"
          aria-label="Search models"
          className="clawk-liquid-panel h-10 w-full rounded-xl pl-9 pr-9 text-sm outline-none placeholder:text-muted-foreground focus:border-[rgb(var(--clawk-liquid-violet)/0.6)]"
        />
        {query && (
          <button
            type="button"
            onClick={() => onQuery("")}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      {aside}
    </div>
  );
}

export function CookbookFilterChips({
  filters,
  onChange,
  hiddenCount,
}: {
  filters: Filters;
  onChange: (next: Filters) => void;
  hiddenCount: number;
}) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const ctx = (value: Filters["ctx"], label: string) => (
    <Chip key={label} active={filters.ctx === value} onClick={() => set({ ctx: filters.ctx === value ? 0 : value })}>
      {label}
    </Chip>
  );
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <Group label="Fit">
        <Chip active={filters.fit === "all"} onClick={() => set({ fit: "all" })}>
          All
        </Chip>
        <Chip active={filters.fit === "fits"} onClick={() => set({ fit: filters.fit === "fits" ? "all" : "fits" })} title="Only models that fit this machine">
          ✓ Fits
        </Chip>
        <Chip active={filters.fit === "no_fit"} onClick={() => set({ fit: filters.fit === "no_fit" ? "all" : "no_fit" })} title="Only models too big for this machine">
          Too big
        </Chip>
      </Group>
      <Group label="Tools">
        <Chip active={filters.tools === "tools"} onClick={() => set({ tools: filters.tools === "tools" ? "all" : "tools" })} title="Only models with function-calling (the agent needs it)">
          tools ✓
        </Chip>
      </Group>
      <Group label="Context">
        {ctx(32768, "32k+")}
        {ctx(131072, "128k+")}
        {ctx(262144, "256k+")}
      </Group>
      <Group label="Backend">
        <Chip active={filters.source === "ollama"} onClick={() => set({ source: filters.source === "ollama" ? "all" : "ollama" })}>
          Ollama
        </Chip>
        <Chip active={filters.source === "gguf"} onClick={() => set({ source: filters.source === "gguf" ? "all" : "gguf" })}>
          llama.cpp
        </Chip>
      </Group>
      {hiddenCount > 0 && <span className="text-xs text-muted-foreground/70">{hiddenCount} hidden by filters</span>}
    </div>
  );
}
