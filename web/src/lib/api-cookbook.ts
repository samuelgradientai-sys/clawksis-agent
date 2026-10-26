// Typed client for /api/cookbook/* (clawk_cli/web_routers/cookbook.py). Model files, servers
// and downloads are machine-level; "use" / "model-use" carry the selected profile (fetchJSON
// adds it — they are in api.ts's PROFILE_SCOPED_PREFIXES).
import { fetchJSON } from "./api";
import type {
  CatalogResponse,
  CookbookModel,
  DownloadProgress,
  HFFile,
  HFRepo,
  InstalledModel,
  InterruptedDownload,
  LlamaCppStatus,
  TransferProgress,
} from "./cookbook";

const post = <T>(path: string, body: unknown) =>
  fetchJSON<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

const q = encodeURIComponent;

export interface ActiveTransfers {
  downloads?: Array<DownloadProgress & { download_id: string }>;
  pulls?: Array<TransferProgress & { tag: string }>;
  interrupted?: InterruptedDownload[];
}

type StartResult = { ok: boolean; status?: string; error?: string };
type UseResult = { ok: boolean; model?: string; error?: string };

export const cookbookApi = {
  catalog: () => fetchJSON<CatalogResponse>("/api/cookbook/catalog"),
  library: () => fetchJSON<CatalogResponse>("/api/cookbook/library"),
  providers: () => fetchJSON<{ llamacpp?: LlamaCppStatus }>("/api/cookbook/providers"),
  installed: () => fetchJSON<{ models: InstalledModel[] }>("/api/cookbook/installed"),
  active: () => fetchJSON<ActiveTransfers>("/api/cookbook/active"),
  search: (term: string) =>
    fetchJSON<{ models: CookbookModel[]; error?: string }>(`/api/cookbook/search?q=${q(term)}`),
  hfSearch: (term: string) =>
    fetchJSON<{ models: HFRepo[]; error?: string }>(`/api/cookbook/hf-search?q=${q(term)}`),
  hfFiles: (repo: string) =>
    fetchJSON<{ files: HFFile[]; error?: string }>(`/api/cookbook/hf-files?repo=${q(repo)}`),
  providerInstall: (provider: string) => post<StartResult>("/api/cookbook/provider-install", { provider }),
  providerInstallStatus: (provider: string) =>
    fetchJSON<{ status: string }>(`/api/cookbook/provider-install-status?provider=${q(provider)}`),
  pull: (tag: string) => post<StartResult>("/api/cookbook/pull", { tag }),
  pullStatus: (tag: string) => fetchJSON<TransferProgress>(`/api/cookbook/pull-status?tag=${q(tag)}`),
  pullCancel: (tag: string) => post<unknown>("/api/cookbook/pull-cancel", { tag }),
  download: (repo: string, file: string) =>
    post<{ ok: boolean; download_id?: string; error?: string }>("/api/cookbook/download", { repo, file }),
  downloadStatus: (id: string) => fetchJSON<DownloadProgress>(`/api/cookbook/download-status?id=${q(id)}`),
  downloadCancel: (id: string) => post<unknown>("/api/cookbook/download-cancel", { id }),
  use: (tag: string) => post<UseResult>("/api/cookbook/use", { tag }),
  modelUse: (provider: string, id: string) => post<UseResult>("/api/cookbook/model-use", { provider, id }),
  modelDelete: (provider: string, id: string) => post<unknown>("/api/cookbook/model-delete", { provider, id }),
  modelVerify: (id: string) =>
    post<{ ok: boolean; error?: string; size_bytes?: number }>("/api/cookbook/model-verify", { id }),
  modelRename: (id: string, name: string) => post<unknown>("/api/cookbook/model-rename", { id, name }),
  llamacppStop: () => post<unknown>("/api/cookbook/llamacpp-stop", {}),
};
