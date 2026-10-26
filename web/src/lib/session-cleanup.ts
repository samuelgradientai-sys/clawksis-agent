/** Form text of the Sessions "Limpiar" dialog, before it becomes a request. */
export interface CleanupFilterText {
  source: string;
  model: string;
  days: string;
  maxMessages: string;
}

export interface CleanupRequest {
  source?: string;
  model?: string;
  older_than_days?: number;
  max_messages?: number;
  dry_run: boolean;
}

const WHOLE = /^\d+$/;

/** The POST /api/sessions/cleanup body for a filter, or null when no filter is set (the backend
 *  requires at least one). Numbers must be whole and >= 0; anything else counts as unset. */
export function buildCleanupRequest(filter: CleanupFilterText, dryRun: boolean): CleanupRequest | null {
  const body: CleanupRequest = { dry_run: dryRun };
  if (filter.source) body.source = filter.source;
  if (filter.model.trim()) body.model = filter.model.trim();
  if (WHOLE.test(filter.days.trim())) body.older_than_days = Number(filter.days.trim());
  if (WHOLE.test(filter.maxMessages.trim())) body.max_messages = Number(filter.maxMessages.trim());
  return Object.keys(body).length > 1 ? body : null; // more than dry_run alone
}

/** Days for a prune: a whole number >= 1 (the backend 400s on less), else null. */
export function parsePruneDays(text: string): number | null {
  const trimmed = text.trim();
  if (!WHOLE.test(trimmed)) return null;
  const days = Number(trimmed);
  return days >= 1 ? days : null;
}
