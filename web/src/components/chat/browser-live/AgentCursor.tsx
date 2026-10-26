/** The agent's pointer over the live frame: where it moves, clicks (a pulse) and types. It fades
 *  out when the agent has been still for a few seconds. */

import { useEffect, useState } from "react";
import type { LiveFrameMetadata } from "@/lib/api-browser-live";
import type { LiveBrowser } from "./useLiveBrowser";

const IDLE_MS = 3500;

interface AgentCursorProps {
  cursor: LiveBrowser["cursor"];
  meta: LiveFrameMetadata;
}

export function AgentCursor({ cursor, meta }: AgentCursorProps) {
  const [idleAt, setIdleAt] = useState(0);
  useEffect(() => {
    if (!cursor) return undefined;
    const timer = window.setTimeout(() => setIdleAt(cursor.at), IDLE_MS);
    return () => window.clearTimeout(timer);
  }, [cursor]);
  if (!cursor || idleAt === cursor.at || !meta.deviceWidth || !meta.deviceHeight) return null;

  const clicking = cursor.kind === "click" || cursor.kind === "down";
  const typing = cursor.kind === "type" || cursor.kind === "focus";
  return (
    <div
      data-testid="agent-cursor"
      data-kind={cursor.kind}
      className="pointer-events-none absolute z-10 ease-out motion-safe:transition-[left,top] motion-safe:duration-200"
      style={{
        left: `${(cursor.x / meta.deviceWidth) * 100}%`,
        top: `${(cursor.y / meta.deviceHeight) * 100}%`,
      }}
    >
      {clicking && (
        <span className="absolute -left-3 -top-3 size-6 rounded-full border-2 border-[#8B6CFF] motion-safe:animate-ping" />
      )}
      <svg width="18" height="22" viewBox="0 0 18 22" className="drop-shadow-[0_1px_2px_rgba(0,0,0,0.6)]">
        <path
          d="M1 1l15 9.5-6.6 1.4L13 20l-3 1.4-3.6-8.1L1 17.5z"
          fill="#6C4FD6"
          stroke="#fff"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
      <span className="absolute left-4 top-4 whitespace-nowrap rounded-full bg-[#6C4FD6] px-1.5 py-0.5 text-[10px] font-medium text-white shadow">
        {typing ? "Escribiendo…" : "Agente"}
      </span>
    </div>
  );
}
