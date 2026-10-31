import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";

import { api, ApiError, unwrap } from "@/api/client";
import { queryKeys, type ChatMessageView, type ProposalView } from "@/api/queries";
import { parseData, parseSSE } from "@/api/sse";

import { chatReducer, initialChatState, type ChatAction, type ChatState } from "./chatReducer";
import { useChatView } from "./ChatViewProvider";
import { parseSlashCommand } from "./slash";
import type { ChatCard, ChatItem, ChatView } from "./types";

const SESSION_KEY = "offerbound.chatSession";

let idCounter = 0;
const nextId = (prefix: string) => `${prefix}-${String(Date.now())}-${String(++idCounter)}`;

function readStoredSession(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function storeSession(id: string | null): void {
  try {
    if (id) localStorage.setItem(SESSION_KEY, id);
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    // The conversation still works; it just won't be restored after a reload.
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function toItems(messages: ChatMessageView[]): ChatItem[] {
  return messages.map((m): ChatItem =>
    m.role === "user"
      ? { kind: "user", id: `m-${String(m.id)}`, text: m.content }
      : {
          kind: "assistant",
          id: `m-${String(m.id)}`,
          text: m.content,
          cards: m.cards as ChatCard[],
          tools: [],
          proposals: [],
          status: "done",
        },
  );
}

interface ChatContextValue extends ChatState {
  view: ChatView;
  busy: boolean;
  openDrawer: () => void;
  closeDrawer: () => void;
  toggleDrawer: () => void;
  send: (text: string) => Promise<void>;
  stop: () => void;
  newConversation: () => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(chatReducer, initialChatState, (s) => ({
    ...s,
    sessionId: readStoredSession(),
  }));
  const view = useChatView();
  const queryClient = useQueryClient();
  const abortRef = useRef<AbortController | null>(null);
  const busy = state.items.some((item) => item.kind === "assistant" && item.status === "streaming");

  // Restore the stored conversation once.
  const restoredFor = useRef<string | null>(null);
  useEffect(() => {
    const sessionId = state.sessionId;
    if (!sessionId || restoredFor.current === sessionId || state.items.length > 0) return;
    restoredFor.current = sessionId;
    api
      .GET("/api/chat/sessions/{session_id}/messages", {
        params: { path: { session_id: sessionId } },
      })
      .then(({ data, response }) => {
        if (data) dispatch({ type: "hydrate", items: toItems(data) });
        else if (response.status === 404) {
          storeSession(null);
          dispatch({ type: "session", sessionId: null });
        }
      })
      .catch(() => undefined);
  }, [state.sessionId, state.items.length]);

  const ensureSession = useCallback(async (): Promise<string> => {
    if (state.sessionId) return state.sessionId;
    const session = await unwrap(api.POST("/api/chat/sessions", { body: {} }));
    storeSession(session.id);
    restoredFor.current = session.id;
    dispatch({ type: "session", sessionId: session.id });
    return session.id;
  }, [state.sessionId]);

  const runSlash = useCallback(
    async (assistantId: string, name: string, params: Record<string, unknown>) => {
      try {
        const out = await unwrap(
          api.POST("/api/commands/{name}", { params: { path: { name } }, body: { params } }),
        );
        const card: ChatCard = out.task_id
          ? { type: "task", task_id: out.task_id, command: name }
          : { type: "command_result", command: name, result: out.result };
        dispatch({ type: "card", id: assistantId, card });
        dispatch({ type: "finish", id: assistantId, status: "done" });
      } catch (error) {
        const message = error instanceof ApiError ? error.message : "The command failed.";
        dispatch({ type: "finish", id: assistantId, status: "error", error: message });
      }
    },
    [],
  );

  const streamReply = useCallback(
    async (assistantId: string, text: string) => {
      const controller = new AbortController();
      abortRef.current = controller;
      const apply = (action: ChatAction) => {
        dispatch(action);
      };
      try {
        const sessionId = await ensureSession();
        const { data, response, error } = await api.POST(
          "/api/chat/sessions/{session_id}/messages",
          {
            params: { path: { session_id: sessionId } },
            body: {
              text,
              view: {
                label: view.label,
                route: view.route,
                job_ids: view.job_ids ?? [],
                application_ids: view.application_ids ?? [],
              },
            },
            parseAs: "stream",
            signal: controller.signal,
          },
        );
        if (!response.ok || !data) {
          throw new ApiError(response.status, str(asRecord(error).detail) || "Chat failed.");
        }
        for await (const message of parseSSE(data)) {
          const payload = asRecord(parseData(message));
          switch (message.event) {
            case "text":
              apply({ type: "text", id: assistantId, text: str(payload.text) });
              break;
            case "tool_call":
              apply({
                type: "tool_call",
                id: assistantId,
                callId: str(payload.id),
                name: str(payload.name),
              });
              break;
            case "tool_result":
              apply({
                type: "tool_result",
                id: assistantId,
                callId: str(payload.id),
                isError: payload.is_error === true,
              });
              break;
            case "card":
              apply({ type: "card", id: assistantId, card: payload.card as ChatCard });
              break;
            case "memory_proposals":
              apply({
                type: "proposals",
                id: assistantId,
                proposals: payload.proposals as ProposalView[],
              });
              void queryClient.invalidateQueries({ queryKey: queryKeys.proposals });
              break;
            case "error":
              apply({
                type: "finish",
                id: assistantId,
                status: "error",
                error: str(payload.message) || "Something went wrong.",
              });
              break;
            case "done":
              apply({ type: "finish", id: assistantId, status: "done" });
              break;
          }
        }
        apply({ type: "finish", id: assistantId, status: "done" });
      } catch (error) {
        if (controller.signal.aborted) {
          apply({ type: "finish", id: assistantId, status: "stopped" });
        } else {
          const message = error instanceof ApiError ? error.message : "Couldn't reach Offerbound.";
          apply({ type: "finish", id: assistantId, status: "error", error: message });
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [ensureSession, queryClient, view],
  );

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || busy) return;
      const assistantId = nextId("a");
      dispatch({ type: "user", id: nextId("u"), text });
      dispatch({ type: "assistant", id: assistantId });
      const slash = parseSlashCommand(text);
      if (slash) await runSlash(assistantId, slash.name, slash.params);
      else await streamReply(assistantId, text);
    },
    [busy, runSlash, streamReply],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const newConversation = useCallback(() => {
    abortRef.current?.abort();
    storeSession(null);
    dispatch({ type: "reset" });
  }, []);

  const value = useMemo<ChatContextValue>(
    () => ({
      ...state,
      view,
      busy,
      openDrawer: () => {
        dispatch({ type: "open" });
      },
      closeDrawer: () => {
        dispatch({ type: "close" });
      },
      toggleDrawer: () => {
        dispatch({ type: "toggle" });
      },
      send,
      stop,
      newConversation,
    }),
    [state, view, busy, send, stop, newConversation],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat(): ChatContextValue {
  const value = useContext(ChatContext);
  if (!value) throw new Error("useChat must be used inside <ChatProvider>");
  return value;
}
