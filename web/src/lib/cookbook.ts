// Cookbook (local models) shapes, formatters and filters — backed by /api/cookbook/*
// (clawk_cli/web_routers/cookbook.py). Pure, so the page's rules are unit-testable.

export interface Fit {
  mode: "gpu" | "cpu" | "none" | "unknown";
  tier: "perfect" | "good" | "marginal" | "no_fit" | "unknown";
  reason: string;
}

export interface CookbookModel {
  id: string;
  name: string;
  family: string;
  params_b: number;
  ollama: string;
  quant: string;
  size_gb: number;
  min_vram_gb: number;
  min_ram_gb: number;
  context: number;
  tool_use: boolean;
  use_case: string;
  fit: Fit;
  installed: boolean;
}

export interface Hardware {
  ram_gb?: number;
  ram_available_gb?: number;
  disk_free_gb?: number;
  load_1m?: number;
  cpu_cores?: number;
  gpu_name?: string;
  vram_gb?: number;
  platform?: string;
  arch?: string;
}

export interface OllamaStatus {
  installed?: boolean;
  running?: boolean;
  models?: string[];
  base_url?: string;
}

export interface InstalledModel {
  id: string;
  name: string;
  provider: string;
  size_bytes?: number;
  path?: string;
  quant?: string;
  repo?: string;
  file?: string;
}

export interface LlamaCppStatus {
  installed?: boolean;
  install_status?: string;
  server?: { running?: boolean; model_file?: string; base_url?: string };
  models_dir?: string;
  models?: InstalledModel[];
}

export interface CatalogResponse {
  hardware: Hardware;
  ollama: OllamaStatus;
  models: CookbookModel[];
  /** A live source (ollama.com) did not answer — not the same as "no results". */
  error?: string;
}

export interface HFRepo {
  repo: string;
  author: string;
  name: string;
  downloads: number;
  likes: number;
  updated_at: string;
  license: string;
  gated: boolean;
  tags: string[];
  /** GGUF metadata Hugging Face extracts (expand[]=gguf); 0 / "" when absent. */
  context: number;
  architecture: string;
  params_b: number;
  size_q4_gb: number;
  tool_use: boolean;
}

export interface HFFile {
  file: string;
  size_bytes: number;
  quant: string;
  multipart: boolean;
}

export interface TransferProgress {
  status: string;
  phase?: string;
  downloaded?: number;
  total?: number;
  percent?: number | null;
  speed_bps?: number;
  eta_seconds?: number | null;
}

export interface DownloadProgress extends TransferProgress {
  repo?: string;
  file?: string;
  error?: string;
  model_id?: string;
}

export interface InterruptedDownload {
  file: string;
  repo: string;
  downloaded: number;
  resumable: boolean;
}

export const TIER_STYLE: Record<Fit["tier"], { label: string; cls: string }> = {
  perfect: { label: "Fits great", cls: "border-emerald-500/50 bg-emerald-500/10 text-emerald-300" },
  good: { label: "Fits", cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" },
  marginal: { label: "Tight / slow", cls: "border-amber-500/50 bg-amber-500/10 text-amber-300" },
  no_fit: { label: "Too big", cls: "border-rose-500/40 bg-rose-500/10 text-rose-300" },
  unknown: { label: "Size unknown", cls: "border-white/15 bg-white/5 text-muted-foreground" },
};

export function fmtBytes(n?: number | null): string {
  if (!n || n <= 0) return "—";
  const gb = n / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(gb >= 10 ? 0 : 1)} GB`;
  return `${(n / 1024 ** 2).toFixed(0)} MB`;
}

export function fmtSpeed(bps?: number): string {
  return bps && bps > 0 ? `${fmtBytes(bps)}/s` : "";
}

export function fmtCtx(tokens?: number): string {
  if (!tokens || tokens <= 0) return "";
  return tokens >= 1000 ? `${Math.round(tokens / 1024)}k` : String(tokens);
}

export function fmtEta(s?: number | null): string {
  if (s == null || s <= 0) return "";
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

const ACTIVE_DOWNLOAD = new Set(["downloading", "verifying", "registering"]);
const ACTIVE_PULL = new Set(["pulling", "validating"]);

export const isActiveDownload = (status?: string) => ACTIVE_DOWNLOAD.has(status ?? "");
export const isActivePull = (status?: string) => ACTIVE_PULL.has(status ?? "");

/** Transfers still running (the Downloads tab badge). */
export function activeTransferCount(
  downloads: Record<string, DownloadProgress>,
  pulls: Record<string, TransferProgress>,
): number {
  return (
    Object.values(downloads).filter((d) => isActiveDownload(d.status)).length +
    Object.values(pulls).filter((p) => isActivePull(p.status)).length
  );
}

/** A transfer that has stopped for good: polling ends, the row keeps its final state. */
export function isFinalTransfer(status?: string): boolean {
  return status === "done" || status === "cancelled" || status === "error" || (status ?? "").startsWith("error");
}

export interface CookbookFilters {
  fit: "all" | "fits" | "no_fit";
  tools: "all" | "tools";
  ctx: 0 | 32768 | 131072 | 262144;
  source: "all" | "ollama" | "gguf";
}

export const DEFAULT_FILTERS: CookbookFilters = { fit: "all", tools: "all", ctx: 0, source: "all" };

export function filtersActive(f: CookbookFilters): boolean {
  return f.fit !== "all" || f.tools !== "all" || f.ctx !== 0 || f.source !== "all";
}

function passesCommon(fits: boolean, toolUse: boolean, context: number, f: CookbookFilters): boolean {
  if (f.fit === "fits" && !fits) return false;
  if (f.fit === "no_fit" && fits) return false;
  if (f.tools === "tools" && !toolUse) return false;
  return !(f.ctx && context < f.ctx);
}

export function ollamaModelVisible(m: CookbookModel, f: CookbookFilters): boolean {
  return f.source !== "gguf" && passesCommon(m.fit.tier !== "no_fit", m.tool_use, m.context, f);
}

/** A GGUF repo "fits" by its Q4 size (from the real parameter count) vs RAM; without metadata
 *  (0) it is not ruled out. */
export function hfRepoFits(r: HFRepo, ramGb: number): boolean {
  return r.size_q4_gb > 0 && ramGb > 0 ? r.size_q4_gb <= ramGb : true;
}

export function hfRepoVisible(r: HFRepo, f: CookbookFilters, ramGb: number): boolean {
  return f.source !== "ollama" && passesCommon(hfRepoFits(r, ramGb), r.tool_use, r.context, f);
}

/** Curated catalog (or the full library) narrowed by a local text match, then the live Ollama
 *  search results the local list does not already hold. */
export function mergeOllamaRows(base: CookbookModel[], remote: CookbookModel[], query: string): CookbookModel[] {
  const q = query.trim().toLowerCase();
  if (!q) return base;
  const local = base.filter((m) => `${m.name} ${m.family} ${m.ollama} ${m.use_case}`.toLowerCase().includes(q));
  const tags = new Set(local.map((m) => m.ollama));
  return [...local, ...remote.filter((m) => !tags.has(m.ollama))];
}

/** Whether *query* reads like a pullable Ollama tag ("qwen3:8b", "user/model") the lists lack. */
export function customPullTag(query: string, models: CookbookModel[]): string | null {
  const tag = query.trim();
  if (!tag || !/^[a-z0-9][a-z0-9._/-]*(:[a-z0-9._-]+)?$/i.test(tag)) return null;
  return models.some((m) => m.ollama.toLowerCase() === tag.toLowerCase()) ? null : tag;
}
