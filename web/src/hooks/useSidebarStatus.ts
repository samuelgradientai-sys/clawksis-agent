import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { StatusResponse } from "@/lib/api";

const POLL_MS = 10_000;

/**
 * Light-weight status poll for the app shell (sidebar). The Status page uses
 * its own faster interval; we keep this slower to avoid duplicate load.
 */
export function useSidebarStatus() {
  const [status, setStatus] = useState<StatusResponse | null>(null);

  useEffect(() => {
    const load = () => {
      // Skip polling while the tab is hidden — refresh on return instead.
      if (document.hidden) return;
      api
        .getStatus()
        .then(setStatus)
        .catch(() => {});
    };
    load();
    const id = setInterval(load, POLL_MS);
    const onVisible = () => {
      if (!document.hidden) load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return status;
}
