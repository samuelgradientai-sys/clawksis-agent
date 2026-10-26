import type { SessionInfo } from "./useChatGateway";

type Payload = Record<string, unknown>;

function finite(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function nonEmpty(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

/** The persisted (DB) key a session event carries. `session.info` names it
 *  `stored_session_id` (tui_gateway/server.py `_session_info`); older payloads
 *  used `session_id`. */
export function storedSessionKey(payload: Payload): string | null {
  return nonEmpty(payload.stored_session_id) ?? nonEmpty(payload.session_id) ?? null;
}

/** A `session.info` event applied to the header state. The gateway sends the
 *  provider as `provider`, the live title as `title` and the context window in
 *  `usage.context_used` / `usage.context_max`; empty values keep what we had. */
export function applySessionInfo(prev: SessionInfo, payload: Payload, liveId: string | null): SessionInfo {
  const usage = (payload.usage && typeof payload.usage === "object" ? payload.usage : {}) as Payload;
  return {
    ...prev,
    sessionId: liveId ?? prev.sessionId,
    sessionKey: storedSessionKey(payload) ?? prev.sessionKey,
    model: nonEmpty(payload.model) ?? prev.model,
    modelProvider: nonEmpty(payload.provider) ?? nonEmpty(payload.model_provider) ?? prev.modelProvider,
    tokensUsed: finite(usage.context_used) ?? finite(payload.tokens_used) ?? prev.tokensUsed,
    tokensMax: finite(usage.context_max) ?? finite(payload.tokens_max) ?? prev.tokensMax,
    title: nonEmpty(payload.title) ?? prev.title,
  };
}

/** The title a `session.title` event announces, or null when it is blank. */
export function titleFromEvent(payload: Payload): string | null {
  return nonEmpty(payload.title)?.trim() ?? null;
}

interface IdRefs {
  liveSid: { current: string | null };
  selectedKey: { current: string | null };
}

/** Remember the live sid and, when nothing else is selected, the stored key of
 *  the session a `session.info` event describes. Returns the live sid. */
export function trackSessionIds(refs: IdRefs, evtSid: string | undefined, payload: Payload): string | null {
  const liveId = evtSid || refs.liveSid.current || null;
  const storedId = storedSessionKey(payload);
  if (liveId) refs.liveSid.current = liveId;
  if (storedId && (!refs.selectedKey.current || refs.selectedKey.current === liveId)) {
    refs.selectedKey.current = storedId;
  }
  return liveId;
}
