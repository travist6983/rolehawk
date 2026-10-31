import { EyeIcon, MessageSquarePlusIcon, SparklesIcon, XIcon } from "lucide-react";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useHotkey, modKeyLabel } from "@/lib/hotkeys";
import { cn } from "@/lib/utils";

import "./cards/cards";
import { ChatInput } from "./ChatInput";
import { useChat } from "./ChatProvider";
import { MessageList } from "./MessageList";

/** Right-side chat drawer: 420px on desktop, full screen below 768px. Non-modal, so the page
 *  stays usable while it's open. Toggle with Cmd/Ctrl+K; Escape closes it. */
export function ChatDrawer() {
  const chat = useChat();
  const input = useRef<HTMLTextAreaElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  useHotkey("k", { mod: true }, () => {
    if (!chat.open) returnFocus.current = document.activeElement as HTMLElement | null;
    chat.toggleDrawer();
  });

  useEffect(() => {
    if (chat.open) {
      input.current?.focus();
    } else if (returnFocus.current) {
      returnFocus.current.focus();
      returnFocus.current = null;
    }
  }, [chat.open]);

  return (
    <>
      <aside
        role="dialog"
        aria-modal="false"
        aria-label="Chat with Claude"
        aria-hidden={!chat.open}
        data-testid="chat-drawer"
        onKeyDown={(event) => {
          if (event.key === "Escape") chat.closeDrawer();
        }}
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l bg-background shadow-xl md:w-[420px]",
          "duration-150 ease-out",
          // Visibility flips instantly on open (so the input can take focus right away) and
          // only after the slide-out on close.
          chat.open
            ? "visible translate-x-0 transition-transform"
            : "invisible translate-x-full transition-[transform,visibility]",
        )}
      >
        <header className="flex items-center gap-2 border-b px-4 py-3">
          <SparklesIcon className="size-4 text-primary" aria-hidden />
          <h2 className="font-semibold">Chat</h2>
          <div className="ml-auto flex gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="New conversation"
                  onClick={chat.newConversation}
                >
                  <MessageSquarePlusIcon />
                </Button>
              </TooltipTrigger>
              <TooltipContent>New conversation</TooltipContent>
            </Tooltip>
            <Button size="icon" variant="ghost" aria-label="Close chat" onClick={chat.closeDrawer}>
              <XIcon />
            </Button>
          </div>
        </header>

        <div className="flex px-4 pt-3">
          <span
            className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground"
            data-testid="context-chip"
          >
            <EyeIcon className="size-3.5 shrink-0" aria-hidden />
            <span className="truncate">Viewing: {chat.view.label}</span>
          </span>
        </div>

        <MessageList
          items={chat.items}
          onPick={(text) => {
            void chat.send(text);
          }}
        />
        <ChatInput
          ref={input}
          busy={chat.busy}
          onSend={(text) => {
            void chat.send(text);
          }}
          onStop={chat.stop}
        />
      </aside>

      {/* Stays mounted while the drawer is open (just hidden) so focus can return to it. */}
      <Button
        className={cn(
          "fixed right-4 bottom-4 z-40 size-12 rounded-full shadow-lg sm:h-11 sm:w-auto sm:px-4",
          chat.open && "hidden",
        )}
        onClick={() => {
          returnFocus.current = document.activeElement as HTMLElement | null;
          chat.openDrawer();
        }}
        aria-label="Open chat"
        aria-keyshortcuts="Meta+K Control+K"
      >
        <SparklesIcon />
        <span className="sr-only sm:not-sr-only">Ask Claude</span>
        <kbd className="ml-1 hidden rounded bg-black/25 px-1.5 font-mono text-[11px] sm:inline">
          {modKeyLabel()}K
        </kbd>
      </Button>
    </>
  );
}
