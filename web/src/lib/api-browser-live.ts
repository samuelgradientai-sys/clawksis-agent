// Live view of the agent's browser (`clawk_cli/web_routers/browser_live.py`): the server screencasts
// the session's browser over CDP — JPEG frames of the tab the agent is working in, plus the tab list —
// and dispatches mouse/keyboard input there when the user takes control.

import { buildWsUrl, fetchJSON } from "./api";

export interface LiveBrowserSession {
  task_id: string;
}

export interface LiveFrameMetadata {
  deviceWidth: number;
  deviceHeight: number;
}

export interface LiveTab {
  active: boolean;
  title: string | null;
  url: string;
}

export type LiveMessage =
  | { type: "frame"; data: string; metadata: LiveFrameMetadata }
  | { type: "tabs"; tabs: LiveTab[] }
  | { type: "status"; connected: boolean };

export async function listLiveBrowsers(): Promise<LiveBrowserSession[]> {
  const res = await fetchJSON<{ sessions: LiveBrowserSession[] }>("/api/browser/live");
  return res.sessions;
}

export function liveBrowserSocketUrl(taskId: string): Promise<string> {
  return buildWsUrl("/api/browser/live/ws", { task: taskId });
}
