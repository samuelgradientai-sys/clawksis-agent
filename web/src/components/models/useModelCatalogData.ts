import { useCallback, useRef, useState } from "react";
import type { ModelOptionsResult } from "@clawk/shared";

import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { modelsApi, type LocalEndpointStatus } from "@/lib/api-models";

interface ReloadOptions {
  /** Bust the backend's model-id caches and live-probe saved endpoints ("Re-detect"). */
  refresh?: boolean;
  /** Re-run the local server probe too (off for cheap refetches such as window focus). */
  probe?: boolean;
}

/**
 * The Models page's view of what the selected profile can run: the provider catalog
 * (`/api/model/options`) and the local server probe (`/api/model/local-status`). The two requests
 * are independent — a failing probe never hides the catalog — and within each, a newer request
 * always wins over a slower older one.
 */
export function useModelCatalogData() {
  const [options, setOptions] = useState<ModelOptionsResult | null>(null);
  const [localStatus, setLocalStatus] = useState<LocalEndpointStatus[] | null>(null);
  const [pending, setPending] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const catalogSeq = useRef(0);
  const probeSeq = useRef(0);

  const track = useCallback(<T,>(work: Promise<T>) => {
    setPending((n) => n + 1);
    return work.finally(() => setPending((n) => n - 1));
  }, []);

  const reload = useCallback(
    ({ refresh = false, probe = true }: ReloadOptions = {}) => {
      const catalogId = ++catalogSeq.current;
      const catalog = track(
        api
          .getModelOptions({ refresh })
          .then((next) => {
            if (catalogId !== catalogSeq.current) return;
            setOptions(next);
            setError(null);
          })
          .catch((e) => {
            if (catalogId === catalogSeq.current) setError(errorMessage(e));
          }),
      );
      if (!probe) return catalog;
      const probeId = ++probeSeq.current;
      const status = track(
        modelsApi
          .getLocalStatus()
          .then((next) => {
            if (probeId === probeSeq.current) setLocalStatus(next.endpoints ?? []);
          })
          // Advisory only: keep the catalog usable and show reachability as unknown.
          .catch(() => {
            if (probeId === probeSeq.current) setLocalStatus([]);
          }),
      );
      return Promise.all([catalog, status]);
    },
    [track],
  );

  return { options, localStatus, loading: pending > 0, error, reload };
}
