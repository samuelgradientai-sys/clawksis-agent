/** One live-browser connection: finds the session to watch (polling while there is none), opens the
 * screencast socket, and exposes the latest frame, the followed tab and a `send` for input. */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  listLiveBrowsers,
  liveBrowserSocketUrl,
  type LiveFrameMetadata,
  type LiveMessage,
  type LiveTab,
} from "@/lib/api-browser-live";
import { pickSession } from "./liveInput";

const POLL_MS = 3000;

/** `ended`: the browser closed (the agent closes it when its turn ends); the last frame stays up. */
export type LiveState = "searching" | "connecting" | "live" | "ended";

export interface LiveBrowser {
  state: LiveState;
  taskId: string | null;
  frame: { src: string; meta: LiveFrameMetadata } | null;
  tab: LiveTab | null;
  send: (event: object) => void;
}

function applyMessage(
  msg: LiveMessage,
  set: {
    frame: (f: LiveBrowser["frame"]) => void;
    tab: (t: LiveTab) => void;
  },
): void {
  if (msg.type === "frame") set.frame({ src: `data:image/jpeg;base64,${msg.data}`, meta: msg.metadata });
  // A closing browser reports no tabs: keep showing the page it was on.
  else if (msg.type === "tabs" && msg.tabs.length) set.tab(msg.tabs.find((t) => t.active) ?? msg.tabs[0]);
}

function useSessionSearch(preferred: string | null, enabled: boolean): string | null {
  const [taskId, setTaskId] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return undefined;
    let stop = false;
    const look = () =>
      listLiveBrowsers()
        .then((sessions) => !stop && setTaskId(pickSession(sessions, preferred)))
        .catch(() => undefined);
    void look();
    const timer = window.setInterval(look, POLL_MS);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [preferred, enabled]);
  return taskId;
}

export function useLiveBrowser(preferred: string | null): LiveBrowser {
  const [connected, setConnected] = useState(false);
  const [frame, setFrame] = useState<LiveBrowser["frame"]>(null);
  const [tab, setTab] = useState<LiveTab | null>(null);
  const [dropped, setDropped] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const taskId = useSessionSearch(preferred, !connected);

  useEffect(() => {
    if (!taskId) return undefined;
    let closed = false;
    let socket: WebSocket | null = null;
    void liveBrowserSocketUrl(taskId).then((url) => {
      if (closed) return;
      socket = new WebSocket(url);
      socketRef.current = socket;
      socket.onopen = () => setConnected(true);
      socket.onmessage = (ev) => {
        if (typeof ev.data !== "string") return;
        applyMessage(JSON.parse(ev.data) as LiveMessage, { frame: setFrame, tab: setTab });
      };
      socket.onclose = () => {
        socketRef.current = null;
        setConnected(false);
        // The session may be gone (4404) or recycled: retry after the search had a chance to update.
        if (!closed) window.setTimeout(() => !closed && setDropped((n) => n + 1), POLL_MS);
      };
    });
    return () => {
      closed = true;
      socket?.close();
    };
  }, [taskId, dropped]);

  const send = useCallback((event: object) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(event));
  }, []);

  const state: LiveState = connected
    ? frame
      ? "live"
      : "connecting"
    : frame
      ? "ended"
      : taskId
        ? "connecting"
        : "searching";
  return { state, taskId, frame, tab, send };
}
