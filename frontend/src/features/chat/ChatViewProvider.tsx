import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router";

import { navItemFor } from "@/app/nav";

import type { ChatView } from "./types";

interface ChatViewValue {
  view: ChatView;
  setOverride: (view: ChatView | null) => void;
}

const ChatViewContext = createContext<ChatViewValue | null>(null);

/** Tracks what the chat is "looking at": the current screen, or a specific job/application
 *  when a page provides one, so "tailor my CV for this" works without naming the job. */
export function ChatViewProvider({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const [override, setOverride] = useState<ChatView | null>(null);

  const value = useMemo<ChatViewValue>(() => {
    const fallback: ChatView = {
      label: navItemFor(location.pathname).label,
      route: location.pathname,
    };
    // An override only applies on the page that set it.
    const active = override?.route === location.pathname ? override : null;
    return { view: active ?? fallback, setOverride };
  }, [override, location.pathname]);

  return <ChatViewContext.Provider value={value}>{children}</ChatViewContext.Provider>;
}

export function useChatView(): ChatView {
  const value = useContext(ChatViewContext);
  if (!value) throw new Error("useChatView must be used inside <ChatViewProvider>");
  return value.view;
}

/** Pages showing one job or application call this to focus the chat on it. */
export function useProvideChatView(view: ChatView | null): void {
  const value = useContext(ChatViewContext);
  if (!value) throw new Error("useProvideChatView must be used inside <ChatViewProvider>");
  const { setOverride } = value;
  const key = JSON.stringify(view);
  useEffect(() => {
    setOverride(view);
    return () => {
      setOverride(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` captures the view's content
  }, [key, setOverride]);
}
