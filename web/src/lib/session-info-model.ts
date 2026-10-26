/**
 * Model identity from a `session.info` payload (also `session.resume`'s `info`), built by
 * `tui_gateway/server.py::_session_info`. The provider travels as `provider`; the chat hook used
 * to read a `model_provider` key the gateway never sends, so the header and the composer's model
 * menu never learned which provider the session runs on.
 */
function nonEmpty(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/** `undefined` when the payload carries no provider (keep the previous value). */
export function sessionInfoProvider(payload: unknown): string | undefined {
  if (!payload || typeof payload !== "object") return undefined;
  const info = payload as { provider?: unknown; model_provider?: unknown };
  return nonEmpty(info.provider) ?? nonEmpty(info.model_provider);
}
