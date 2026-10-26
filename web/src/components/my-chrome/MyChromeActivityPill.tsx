/** A small persistent pill on every dashboard page while the agent is driving the user's own
 *  Chrome: "El agente está usando tu Chrome · Ver en vivo" takes them to the live view. Not on
 *  the modern chat, where the "Navegador" panel is one tap away; "Ocultar aviso" holds until
 *  the agent stops and starts again. */

import { useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { Chromium, X } from "lucide-react";
import { useChatMode } from "@/components/chat/hooks/useChatMode";
import { useProfileScope } from "@/contexts/useProfileScope";
import { openLiveView, shouldShowPill } from "./activity";
import { myChromeCopy as copy } from "./copy";
import { useMyChromeActivity } from "./useMyChromeActivity";

export function MyChromeActivityPill() {
  const { profile } = useProfileScope();
  const { active, since } = useMyChromeActivity(profile);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [chatMode] = useChatMode();
  const [dismissedFor, setDismissedFor] = useState(0);
  const dismissed = active && dismissedFor === since;

  if (!shouldShowPill({ active, dismissed, pathname, chatMode })) return null;
  return (
    <div
      role="status"
      className="fixed inset-x-3 bottom-3 z-50 mx-auto flex max-w-sm items-center gap-2 rounded-full border border-[#6C4FD6]/60 bg-background/90 py-1.5 pl-3 pr-1.5 text-sm shadow-lg backdrop-blur-xl sm:inset-x-auto sm:right-4 sm:bottom-4"
    >
      <span className="size-2 shrink-0 rounded-full bg-emerald-400 motion-safe:animate-pulse" aria-hidden />
      <Chromium className="h-4 w-4 shrink-0 text-midground" aria-hidden />
      <span className="min-w-0 flex-1 truncate">{copy.pillText}</span>
      <button
        type="button"
        onClick={() => openLiveView(navigate)}
        className="shrink-0 rounded-full bg-[#6C4FD6] px-3 py-1 text-xs font-medium text-white transition-opacity hover:opacity-90"
      >
        {copy.pillAction}
      </button>
      <button
        type="button"
        onClick={() => setDismissedFor(since)}
        aria-label={copy.pillDismiss}
        className="shrink-0 rounded-full p-1 text-muted-foreground transition-colors hover:text-foreground"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}
