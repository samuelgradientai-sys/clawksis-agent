import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";

/**
 * ``cron.archive_chat_sessions`` of *profile* (its config.yaml): when on, each run's chat session
 * is archived at end-of-run so scheduled jobs do not flood the conversations list. ``null`` while
 * the current value loads. The toggle is optimistic and reverts on a failed save.
 */
export function useCronArchiveChats(profile: string, onError: (message: string) => void) {
  const [archiveChats, setArchiveChats] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getConfig(profile)
      .then((cfg) => {
        if (alive) setArchiveChats(Boolean((cfg.cron as Record<string, unknown> | undefined)?.archive_chat_sessions));
      })
      .catch(() => alive && setArchiveChats(false));
    return () => {
      alive = false;
    };
  }, [profile]);

  const toggle = useCallback(
    async (next: boolean) => {
      setArchiveChats(next);
      try {
        // Read-modify-write the full config (the PUT replaces it whole).
        const cfg = await api.getConfig(profile);
        const cron = { ...((cfg.cron ?? {}) as Record<string, unknown>), archive_chat_sessions: next };
        await api.saveConfig({ ...cfg, cron }, profile);
      } catch (e) {
        setArchiveChats(!next);
        onError(`No se pudo guardar la configuración: ${errorMessage(e)}`);
      }
    },
    [onError, profile],
  );

  return [archiveChats, toggle] as const;
}
