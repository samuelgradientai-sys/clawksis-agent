import type { LogFileInfo } from "./api-logs";

/** Always offered, even before they are first written (the page's historical set). */
export const CORE_LOG_FILES = ["agent", "errors", "gateway"];

/**
 * The log files the Logs page offers, in the backend's order: the core three always, any other
 * log `clawk logs` knows once it exists for the selected profile, and the current selection (a
 * `?file=` deep link to a log not written yet must still show as selected). Before the inventory
 * loads (or on an older backend without it) the core set stands in.
 */
export function logFileOptions(files: LogFileInfo[] | null, current: string): string[] {
  const names = files
    ? files
        .filter((f) => f.exists || CORE_LOG_FILES.includes(f.name) || f.name === current)
        .map((f) => f.name)
    : [...CORE_LOG_FILES];
  return names.includes(current) || !current ? names : [...names, current];
}

/** Whether a scroll container is (within a line or so of) its bottom: auto-refresh only follows
 * the tail when the reader is already there, instead of yanking them back from what they read. */
export function isNearBottom(el: Pick<HTMLElement, "scrollTop" | "scrollHeight" | "clientHeight">): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 32;
}
