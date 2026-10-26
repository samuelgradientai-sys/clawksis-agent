/** Live-browser connections: `useLiveSessions` polls the open browsers (the agent's and its
 * subagents'); `useLiveBrowser` streams one of them — frame, tabs, the agent's cursor — and exposes
 * `send` for input plus tab pinning. `thumb` opens a small, input-less preview for the mosaic. */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  listLiveBrowsers,
  liveBrowserSocketUrl,
  type LiveBrowserSession,
  type LiveCursor,
  type LiveFrameMetadata,
  type LiveMessage,
  type LiveTab,
} from "@/lib/api-browser-live";

const POLL_MS = 3000;
const FAST_POLL_MS = 1000;

/** `ended`: the browser closed (the agent closes it when its turn ends); the last frame stays up. */
export type LiveState = "searching" | "connecting" | "live" | "ended";

export interface LiveBrowser {
  state: LiveState;
  taskId: string | null;
  frame: { src: string; meta: LiveFrameMetadata } | null;
  tabs: LiveTab[];
  tab: LiveTab | null;
  /** The viewer chose a tab instead of following the agent. */
  pinned: boolean;
  cursor: (LiveCursor & { at: number }) | null;
  send: (event: object) => void;
  focusTab: (id: string) => void;
  followAgent: () => void;
}

interface Setters {
  frame: (f: NonNullable<LiveBrowser["frame"]>) => void;
  tabs: (tabs: LiveTab[], pinned: boolean) => void;
  cursor: (c: NonNullable<LiveBrowser["cursor"]>) => void;
}

/** A value tagged with the session it came from: switching sessions hides the previous one's state,
 *  while a session that just closed (taskId → null) keeps its last frame on screen. */
interface Tagged<T> {
  task: string;
  value: T;
}

function current<T>(tagged: Tagged<T> | null, taskId: string | null): T | null {
  return tagged && (taskId === null || tagged.task === taskId) ? tagged.value : null;
}

function applyMessage(msg: LiveMessage, set: Setters): void {
  if (msg.type === "frame") set.frame({ src: `data:image/jpeg;base64,${msg.data}`, meta: msg.metadata });
  // A closing browser reports no tabs: keep showing the page it was on.
  else if (msg.type === "tabs" && msg.tabs.length) set.tabs(msg.tabs, msg.pinned);
  else if (msg.type === "cursor") set.cursor({ kind: msg.kind, x: msg.x, y: msg.y, at: Date.now() });
}

const SAME_SESSIONS = (a: LiveBrowserSession[], b: LiveBrowserSession[]) =>
  a.length === b.length && a.every((s, i) => s.task_id === b[i].task_id);

/** Open browsers, polled — quickly while there is none yet (the agent's browser is starting up). */
export function useLiveSessions(): LiveBrowserSession[] {
  const [sessions, setSessions] = useState<LiveBrowserSession[]>([]);
  const idle = sessions.length === 0;
  useEffect(() => {
    let stop = false;
    const look = () =>
      listLiveBrowsers()
        .then((next) => !stop && setSessions((prev) => (SAME_SESSIONS(prev, next) ? prev : next)))
        .catch(() => undefined);
    void look();
    const timer = window.setInterval(look, idle ? FAST_POLL_MS : POLL_MS);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [idle]);
  return sessions;
}

export function useLiveBrowser(taskId: string | null, thumb = false): LiveBrowser {
  const [connected, setConnected] = useState(false);
  const [frame, setFrame] = useState<Tagged<NonNullable<LiveBrowser["frame"]>> | null>(null);
  const [tabs, setTabs] = useState<Tagged<{ tabs: LiveTab[]; pinned: boolean }> | null>(null);
  const [cursor, setCursor] = useState<Tagged<NonNullable<LiveBrowser["cursor"]>> | null>(null);
  const [dropped, setDropped] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!taskId) return undefined;
    let closed = false;
    let socket: WebSocket | null = null;
    const task = taskId;
    const set: Setters = {
      frame: (value) => setFrame({ task, value }),
      tabs: (next, isPinned) => setTabs({ task, value: { tabs: next, pinned: isPinned } }),
      cursor: (value) => setCursor({ task, value }),
    };
    void liveBrowserSocketUrl(taskId, thumb).then((url) => {
      if (closed) return;
      socket = new WebSocket(url);
      socketRef.current = socket;
      socket.onopen = () => setConnected(true);
      socket.onmessage = (ev) => {
        if (typeof ev.data === "string") applyMessage(JSON.parse(ev.data) as LiveMessage, set);
      };
      socket.onclose = () => {
        socketRef.current = null;
        setConnected(false);
        // The session may be gone (4404) or recycled: retry after the session list had a chance to update.
        if (!closed) window.setTimeout(() => !closed && setDropped((n) => n + 1), POLL_MS);
      };
    });
    return () => {
      closed = true;
      socket?.close();
    };
  }, [taskId, thumb, dropped]);

  const send = useCallback((event: object) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(event));
  }, []);
  const focusTab = useCallback((id: string) => send({ type: "focus_tab", id }), [send]);
  const followAgent = useCallback(() => send({ type: "follow_agent" }), [send]);

  const shownFrame = current(frame, taskId);
  const shownTabs = current(tabs, taskId);
  const state: LiveState = connected
    ? shownFrame
      ? "live"
      : "connecting"
    : shownFrame
      ? "ended"
      : taskId
        ? "connecting"
        : "searching";
  const tabList = shownTabs?.tabs ?? [];
  return {
    state,
    taskId,
    frame: shownFrame,
    tabs: tabList,
    tab: tabList.find((t) => t.active) ?? tabList[0] ?? null,
    pinned: shownTabs?.pinned ?? false,
    cursor: connected ? current(cursor, taskId) : null,
    send,
    focusTab,
    followAgent,
  };
}
