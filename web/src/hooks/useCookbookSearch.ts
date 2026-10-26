import { useCallback, useEffect, useState } from "react";
import { cookbookApi } from "@/lib/api-cookbook";
import { errorMessage } from "@/lib/api-error";
import type { CookbookModel, HFRepo } from "@/lib/cookbook";

interface LiveResult<T> {
  rows: T[];
  loading: boolean;
  /** The source did not answer — say "unreachable", never "no models match". */
  error: string | null;
}

const IDLE = { rows: [], loading: false, error: null };

/** Debounced live lookup of *term* against one source; setState only inside the timer. */
function useLive<T>(
  term: string,
  minLength: number,
  fetcher: (term: string) => Promise<{ models: T[]; error?: string }>,
): LiveResult<T> {
  const [state, setState] = useState<LiveResult<T>>(IDLE);
  useEffect(() => {
    const active = term.length >= minLength;
    let alive = true;
    const handle = setTimeout(
      () => {
        if (!active) {
          setState(IDLE);
          return;
        }
        setState((prev) => ({ ...prev, loading: true }));
        fetcher(term)
          .then((res) => alive && setState({ rows: res.models ?? [], loading: false, error: res.error ?? null }))
          .catch((e) => alive && setState({ rows: [], loading: false, error: errorMessage(e) }));
      },
      active ? 450 : 0,
    );
    return () => {
      alive = false;
      clearTimeout(handle);
    };
  }, [term, minLength, fetcher]);
  return state;
}

/** Live search across the Ollama library and Hugging Face GGUF repos, plus "browse all Ollama". */
export function useCookbookSearch(query: string) {
  const term = query.trim();
  const ollama = useLive<CookbookModel>(term, 1, cookbookApi.search);
  const hf = useLive<HFRepo>(term, 2, cookbookApi.hfSearch);
  const [browseAll, setBrowseAll] = useState(false);
  const [library, setLibrary] = useState<CookbookModel[] | null>(null);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);

  const loadLibrary = useCallback(async () => {
    if (library) {
      setBrowseAll(true);
      return;
    }
    setLibraryLoading(true);
    try {
      const res = await cookbookApi.library();
      setLibraryError(res.error ?? null);
      if (!res.error) {
        setLibrary(res.models ?? []);
        setBrowseAll(true);
      }
    } catch (e) {
      setLibraryError(errorMessage(e));
    } finally {
      setLibraryLoading(false);
    }
  }, [library]);

  return { ollama, hf, browseAll, setBrowseAll, library, libraryLoading, libraryError, loadLibrary };
}
