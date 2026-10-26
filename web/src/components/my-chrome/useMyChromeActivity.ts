import { useEffect, useState } from "react";
import { myChromeApi } from "@/lib/api-my-chrome";

const POLL_CONNECTED_MS = 4000;
const POLL_IDLE_MS = 15000;

export interface MyChromeActivityState {
  active: boolean;
  /** When the current stretch of agent activity began (ms), 0 while idle: a dismissal holds for
   *  one stretch only. */
  since: number;
}

const IDLE: MyChromeActivityState = { active: false, since: 0 };

/** Whether the agent is using the user's Chrome right now — polled, quicker while connected. */
export function useMyChromeActivity(profile: string): MyChromeActivityState {
  const [state, setState] = useState<MyChromeActivityState>(IDLE);
  useEffect(() => {
    let stop = false;
    let timer = 0;
    const look = async () => {
      const next = await myChromeApi.activity().catch(() => ({ connected: false, active: false }));
      if (stop) return;
      setState((prev) =>
        next.active ? { active: true, since: prev.active ? prev.since : Date.now() } : IDLE,
      );
      timer = window.setTimeout(() => void look(), next.connected ? POLL_CONNECTED_MS : POLL_IDLE_MS);
    };
    void look();
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, [profile]);
  return state;
}
