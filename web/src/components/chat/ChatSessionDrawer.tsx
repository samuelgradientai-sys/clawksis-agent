/**
 * The conversation list: inline beside the chat from `md` up, an off-canvas
 * drawer on phones (opened from the header, closed by picking a conversation,
 * starting one, tapping outside or Escape). The drawer is portalled to
 * <body>: the dashboard shell wraps routes in a stacking context, so a fixed
 * overlay inside it would slide under the shell's top bar.
 */

import { useEffect, type ComponentProps } from "react";
import { createPortal } from "react-dom";
import { MessagesSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { SessionSidebar } from "./SessionSidebar";
import { PHONE_QUERY, setChatDrawerOpen, useChatDrawerOpen, useMediaQuery } from "./chatDrawerStore";

type SidebarProps = ComponentProps<typeof SessionSidebar>;

const close = () => setChatDrawerOpen(false);

function PhoneDrawer({ open, children }: { open: boolean; children: React.ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return createPortal(
    <div className="clawk-chat-root">
      {open && (
        <button
          type="button"
          aria-label="Cerrar conversaciones"
          onClick={close}
          className="fixed inset-0 z-[80] bg-black/55 backdrop-blur-[2px]"
        />
      )}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-[90] flex max-w-[85vw] bg-background/95 pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)] shadow-2xl shadow-black/50 transition-[transform,visibility] duration-200",
          open ? "visible translate-x-0" : "invisible -translate-x-full",
        )}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}

export function ChatSessionDrawer(props: SidebarProps) {
  const open = useChatDrawerOpen();
  const phone = useMediaQuery(PHONE_QUERY);

  // Leaving the phone layout (rotation, resize) must not leave a stale overlay.
  useEffect(() => {
    if (!phone) close();
  }, [phone]);

  const sidebar = (
    <SessionSidebar
      {...props}
      onSelectSession={(id) => {
        close();
        props.onSelectSession(id);
      }}
      onNewChat={() => {
        close();
        props.onNewChat();
      }}
      onNewChatInProject={(projectId) => {
        close();
        props.onNewChatInProject(projectId);
      }}
    />
  );
  return phone ? <PhoneDrawer open={open}>{sidebar}</PhoneDrawer> : sidebar;
}

/** The header's button that opens the list on phones (hidden from `md` up). */
export function ChatDrawerButton() {
  const open = useChatDrawerOpen();
  return (
    <button
      type="button"
      aria-label="Conversaciones"
      aria-expanded={open}
      onClick={() => setChatDrawerOpen(true)}
      className="clawk-liquid-chip flex size-11 shrink-0 items-center justify-center rounded-xl border border-white/10 text-foreground md:hidden"
    >
      <MessagesSquare className="size-4" />
    </button>
  );
}
