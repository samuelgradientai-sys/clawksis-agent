// "The agent is using your Chrome" outside the chat: when to show the pill, and the one action it
// has — take the user to the chat with the "Navegador" panel open.

import { setChatMode, type ChatMode } from "@/components/chat/hooks/useChatMode";
import { setSidePanel } from "@/components/chat/sidePanelStore";

export interface PillContext {
  active: boolean;
  dismissed: boolean;
  pathname: string;
  chatMode: ChatMode;
}

/** The modern chat is on screen: its "Navegador" panel opens itself on the first browser tool of
 *  a turn and stays one tap away, so a pill there would only fight a user who closed it. */
export function inModernChat({ pathname, chatMode }: PillContext): boolean {
  return pathname.replace(/\/$/, "") === "/chat" && chatMode === "modern";
}

export function shouldShowPill(ctx: PillContext): boolean {
  return ctx.active && !ctx.dismissed && !inModernChat(ctx);
}

/** Open the live view: the chat (its current conversation) in modern mode, "Navegador" panel. */
export function openLiveView(navigate: (path: string) => void): void {
  setChatMode("modern");
  setSidePanel("browser");
  navigate("/chat");
}
