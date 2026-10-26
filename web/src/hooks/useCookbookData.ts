import { useCallback, useEffect, useRef, useState } from "react";
import { getManagementProfile } from "@/lib/api";
import { cookbookApi } from "@/lib/api-cookbook";
import { errorMessage } from "@/lib/api-error";
import { fmtBytes, type CatalogResponse, type CookbookModel, type InstalledModel, type LlamaCppStatus } from "@/lib/cookbook";

export interface CookbookNotice {
  tone: "info" | "success" | "warning" | "error";
  text: string;
}

const profileName = () => getManagementProfile() || "default";

/**
 * Catalog + hardware, backend status (Ollama / llama.cpp), the installed-models list, backend
 * installs (polled until done), and the model actions (use / verify / rename / delete / stop).
 * Every failure lands in ``notice`` with the backend's reason — nothing fails silently.
 */
export function useCookbookData() {
  const [data, setData] = useState<CatalogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [llamacpp, setLlamacpp] = useState<LlamaCppStatus>({});
  const [installed, setInstalled] = useState<InstalledModel[]>([]);
  const [installedLoading, setInstalledLoading] = useState(false);
  // provider -> "" | "installing" | "done" | "error: ..."
  const [installing, setInstalling] = useState<Record<string, string>>({});
  const [busyModel, setBusyModel] = useState<string | null>(null);
  const [notice, setNotice] = useState<CookbookNotice | null>(null);
  const installTimers = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  useEffect(() => {
    const live = installTimers.current;
    return () => {
      for (const t of Object.values(live)) clearInterval(t);
    };
  }, []);

  const load = useCallback(async () => {
    try {
      setData(await cookbookApi.catalog());
      setLoadError(null);
    } catch (e) {
      setLoadError(errorMessage(e));
    } finally {
      setLoading(false);
    }
    cookbookApi
      .providers()
      .then((prov) => setLlamacpp(prov.llamacpp ?? {}))
      .catch(() => {}); // backend status is decoration for the cards
  }, []);

  const loadInstalled = useCallback(async () => {
    setInstalledLoading(true);
    try {
      setInstalled((await cookbookApi.installed()).models ?? []);
    } catch (e) {
      setNotice({ tone: "error", text: `Could not list installed models: ${errorMessage(e)}` });
    } finally {
      setInstalledLoading(false);
    }
  }, []);

  const pollInstall = useCallback(
    (provider: string) => {
      if (installTimers.current[provider]) return;
      installTimers.current[provider] = setInterval(() => {
        cookbookApi
          .providerInstallStatus(provider)
          .then(({ status }) => {
            setInstalling((prev) => ({ ...prev, [provider]: status }));
            if (status !== "done" && !status.startsWith("error")) return;
            clearInterval(installTimers.current[provider]);
            delete installTimers.current[provider];
            if (status === "done") void load();
          })
          .catch(() => {}); // transient: keep polling
      }, 3000);
    },
    [load],
  );

  const installProvider = useCallback(
    async (provider: string) => {
      setNotice(null);
      setInstalling((prev) => ({ ...prev, [provider]: "installing" }));
      try {
        const res = await cookbookApi.providerInstall(provider);
        if (!res.ok) {
          setInstalling((prev) => ({ ...prev, [provider]: `error: ${res.error ?? "failed"}` }));
        } else if (res.status === "done") {
          setInstalling((prev) => ({ ...prev, [provider]: "done" }));
          void load();
        } else {
          pollInstall(provider);
        }
      } catch (e) {
        setInstalling((prev) => ({ ...prev, [provider]: `error: ${errorMessage(e)}` }));
      }
    },
    [load, pollInstall],
  );

  /** Run a model action with the row marked busy; failures become an error notice. */
  const withBusy = useCallback(async (id: string, what: string, fn: () => Promise<void>) => {
    setBusyModel(id);
    try {
      await fn();
    } catch (e) {
      setNotice({ tone: "error", text: `${what} failed: ${errorMessage(e)}` });
    } finally {
      setBusyModel(null);
    }
  }, []);

  const applyOllamaModel = useCallback(
    (model: CookbookModel) =>
      withBusy(model.id, "Switching model", async () => {
        await cookbookApi.use(model.ollama);
        setNotice(
          model.tool_use
            ? { tone: "success", text: `Profile "${profileName()}" now uses ${model.name} (${model.ollama}) via Ollama.` }
            : {
                tone: "warning",
                text: `Profile "${profileName()}" now uses ${model.name}, but it has NO tool support — the agent fails the moment it needs a tool. Prefer a model marked "tools".`,
              },
        );
      }),
    [withBusy],
  );

  const applyInstalledModel = useCallback(
    (m: InstalledModel) =>
      withBusy(m.id, "Switching model", async () => {
        if (m.provider === "llamacpp") {
          setNotice({ tone: "info", text: "Starting llama-server with this model… the first load can take a while." });
        }
        const res = await cookbookApi.modelUse(m.provider, m.id);
        const via = m.provider === "llamacpp" ? "llama.cpp server" : "Ollama";
        setNotice({ tone: "success", text: `Profile "${profileName()}" now uses ${res.model ?? m.name} (${via}).` });
        void load();
      }),
    [load, withBusy],
  );

  const deleteInstalled = useCallback(
    (m: InstalledModel) =>
      withBusy(m.id, "Delete", async () => {
        await cookbookApi.modelDelete(m.provider, m.id);
        setNotice({ tone: "success", text: `Deleted ${m.name}.` });
        void loadInstalled();
        void load();
      }),
    [load, loadInstalled, withBusy],
  );

  const verifyInstalled = useCallback(
    (m: InstalledModel) =>
      withBusy(m.id, "Verify", async () => {
        const res = await cookbookApi.modelVerify(m.id);
        setNotice(
          res.ok
            ? { tone: "success", text: `${m.name}: file intact (${fmtBytes(res.size_bytes)}).` }
            : { tone: "error", text: `${m.name}: ${res.error ?? "verification failed"}` },
        );
      }),
    [withBusy],
  );

  const renameInstalled = useCallback(
    (m: InstalledModel, name: string) =>
      withBusy(m.id, "Rename", async () => {
        await cookbookApi.modelRename(m.id, name);
        void loadInstalled();
      }),
    [loadInstalled, withBusy],
  );

  const stopServer = useCallback(
    () =>
      withBusy("llamacpp-server", "Stopping llama-server", async () => {
        await cookbookApi.llamacppStop();
        setNotice({ tone: "info", text: "llama-server stopped — its RAM is free again." });
        void load();
      }),
    [load, withBusy],
  );

  return {
    data,
    loading,
    loadError,
    llamacpp,
    installed,
    installedLoading,
    installing,
    busyModel,
    notice,
    setNotice,
    load,
    loadInstalled,
    installProvider,
    applyOllamaModel,
    applyInstalledModel,
    deleteInstalled,
    verifyInstalled,
    renameInstalled,
    stopServer,
  };
}
