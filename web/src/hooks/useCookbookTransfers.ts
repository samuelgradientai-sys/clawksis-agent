import { useCallback, useEffect, useRef, useState } from "react";
import { cookbookApi } from "@/lib/api-cookbook";
import { errorMessage } from "@/lib/api-error";
import {
  isActiveDownload,
  isActivePull,
  isFinalTransfer,
  type DownloadProgress,
  type InterruptedDownload,
  type TransferProgress,
} from "@/lib/cookbook";

type Timers = Record<string, ReturnType<typeof setInterval>>;

/**
 * Ollama pulls and GGUF downloads. Both run in SERVER threads, so leaving the page does not
 * stop them: on mount the hook re-attaches to whatever is still in flight (and keeps the last
 * state of ones that ended, errors included), then polls each until it stops for good.
 * ``onDone`` runs once per transfer that completed (refresh the catalog / installed list).
 */
export function useCookbookTransfers(onDone: (kind: "pull" | "download", progress: DownloadProgress) => void) {
  const [pulls, setPulls] = useState<Record<string, TransferProgress>>({});
  const [downloads, setDownloads] = useState<Record<string, DownloadProgress>>({});
  const [interrupted, setInterrupted] = useState<InterruptedDownload[]>([]);
  const timers = useRef<Timers>({});
  const onDoneRef = useRef(onDone);

  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    const live = timers.current;
    return () => {
      for (const t of Object.values(live)) clearInterval(t);
    };
  }, []);

  const stop = (key: string) => {
    clearInterval(timers.current[key]);
    delete timers.current[key];
  };

  const pollPull = useCallback((tag: string) => {
    const key = `pull:${tag}`;
    if (timers.current[key]) return;
    timers.current[key] = setInterval(() => {
      cookbookApi
        .pullStatus(tag)
        .then((res) => {
          setPulls((prev) => ({ ...prev, [tag]: res }));
          if (!isFinalTransfer(res.status)) return;
          stop(key);
          if (res.status === "done") onDoneRef.current("pull", res);
        })
        .catch(() => {}); // transient: keep polling
    }, 1500);
  }, []);

  const pollDownload = useCallback((id: string) => {
    const key = `dl:${id}`;
    if (timers.current[key]) return;
    timers.current[key] = setInterval(() => {
      cookbookApi
        .downloadStatus(id)
        .then((res) => {
          setDownloads((prev) => ({ ...prev, [id]: res }));
          if (!isFinalTransfer(res.status)) return;
          stop(key);
          if (res.status === "done") onDoneRef.current("download", res);
        })
        .catch(() => {});
    }, 1000);
  }, []);

  const reattach = useCallback(async () => {
    try {
      const res = await cookbookApi.active();
      setInterrupted(res.interrupted ?? []);
      for (const d of res.downloads ?? []) {
        setDownloads((prev) => ({ ...prev, [d.download_id]: d }));
        if (isActiveDownload(d.status)) pollDownload(d.download_id);
      }
      for (const p of res.pulls ?? []) {
        setPulls((prev) => ({ ...prev, [p.tag]: p }));
        if (isActivePull(p.status)) pollPull(p.tag);
      }
    } catch {
      // older server without /active: nothing to re-attach
    }
  }, [pollDownload, pollPull]);

  const pull = useCallback(
    async (tag: string) => {
      setPulls((prev) => ({ ...prev, [tag]: { status: "pulling" } }));
      try {
        const res = await cookbookApi.pull(tag);
        if (!res.ok) {
          setPulls((prev) => ({ ...prev, [tag]: { status: `error: ${res.error ?? "failed"}` } }));
          return;
        }
        pollPull(tag);
      } catch (e) {
        setPulls((prev) => ({ ...prev, [tag]: { status: `error: ${errorMessage(e)}` } }));
      }
    },
    [pollPull],
  );

  const download = useCallback(
    async (repo: string, file: string): Promise<string | null> => {
      try {
        const res = await cookbookApi.download(repo, file);
        if (!res.ok || !res.download_id) return res.error ?? "the download did not start";
        setDownloads((prev) => ({ ...prev, [res.download_id!]: { status: "downloading", repo, file } }));
        setInterrupted((prev) => prev.filter((it) => it.file !== file));
        pollDownload(res.download_id);
        return null;
      } catch (e) {
        return errorMessage(e);
      }
    },
    [pollDownload],
  );

  // A cancel's outcome arrives through the poll (status "cancelled", partial data kept).
  const cancelPull = useCallback((tag: string) => void cookbookApi.pullCancel(tag).catch(() => {}), []);
  const cancelDownload = useCallback((id: string) => void cookbookApi.downloadCancel(id).catch(() => {}), []);

  return { pulls, downloads, interrupted, reattach, pull, download, cancelPull, cancelDownload };
}
