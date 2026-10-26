// Live view of the agent's browser (`clawk_cli/web_routers/browser_live.py`): the server screencasts
// the session's browser over CDP — JPEG frames of the tab the agent is working in (or the one the
// viewer pinned), the tab list and the agent's cursor — and dispatches mouse/keyboard input there when
// the user takes control. `thumb` asks for a small, input-less preview (the mosaic).

import { buildWsUrl, fetchJSON } from "./api";

export interface LiveBrowserSession {
  task_id: string;
}

export interface LiveFrameMetadata {
  deviceWidth: number;
  deviceHeight: number;
}

export interface LiveTab {
  id: string;
  active: boolean;
  title: string | null;
  url: string;
}

/** Where the agent's pointer/keys just landed, in page CSS pixels (the frame's device size). */
export interface LiveCursor {
  kind: "move" | "down" | "click" | "focus" | "type" | "scroll";
  x: number;
  y: number;
}

export type LiveMessage =
  | { type: "frame"; data: string; metadata: LiveFrameMetadata }
  | { type: "tabs"; tabs: LiveTab[]; pinned: boolean }
  | ({ type: "cursor" } & LiveCursor)
  | { type: "status"; connected: boolean };

export async function listLiveBrowsers(): Promise<LiveBrowserSession[]> {
  const res = await fetchJSON<{ sessions: LiveBrowserSession[] }>("/api/browser/live");
  return res.sessions;
}

export function liveBrowserSocketUrl(taskId: string, thumb = false): Promise<string> {
  return buildWsUrl("/api/browser/live/ws", thumb ? { task: taskId, thumb: "1" } : { task: taskId });
}
