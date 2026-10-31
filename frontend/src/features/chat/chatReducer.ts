import type { AssistantStatus, ChatCard, ChatItem, ProposalView } from "./types";

export interface ChatState {
  open: boolean;
  sessionId: string | null;
  items: ChatItem[];
}

export type ChatAction =
  | { type: "open" }
  | { type: "close" }
  | { type: "toggle" }
  | { type: "session"; sessionId: string | null }
  | { type: "hydrate"; items: ChatItem[] }
  | { type: "user"; id: string; text: string }
  | { type: "assistant"; id: string }
  | { type: "text"; id: string; text: string }
  | { type: "tool_call"; id: string; callId: string; name: string }
  | { type: "tool_result"; id: string; callId: string; isError: boolean }
  | { type: "card"; id: string; card: ChatCard }
  | { type: "proposals"; id: string; proposals: ProposalView[] }
  | { type: "finish"; id: string; status: AssistantStatus; error?: string }
  | { type: "reset" };

export const initialChatState: ChatState = { open: false, sessionId: null, items: [] };

function updateAssistant(
  state: ChatState,
  id: string,
  update: (item: Extract<ChatItem, { kind: "assistant" }>) => ChatItem,
): ChatState {
  return {
    ...state,
    items: state.items.map((item) =>
      item.kind === "assistant" && item.id === id ? update(item) : item,
    ),
  };
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "open":
      return { ...state, open: true };
    case "close":
      return { ...state, open: false };
    case "toggle":
      return { ...state, open: !state.open };
    case "session":
      return { ...state, sessionId: action.sessionId };
    case "hydrate":
      return { ...state, items: action.items };
    case "reset":
      return { ...state, sessionId: null, items: [] };
    case "user":
      return {
        ...state,
        items: [...state.items, { kind: "user", id: action.id, text: action.text }],
      };
    case "assistant":
      return {
        ...state,
        items: [
          ...state.items,
          {
            kind: "assistant",
            id: action.id,
            text: "",
            cards: [],
            tools: [],
            proposals: [],
            status: "streaming",
          },
        ],
      };
    case "text":
      return updateAssistant(state, action.id, (item) => ({
        ...item,
        text: item.text + action.text,
      }));
    case "tool_call":
      return updateAssistant(state, action.id, (item) => ({
        ...item,
        tools: [...item.tools, { id: action.callId, name: action.name, status: "running" }],
      }));
    case "tool_result":
      return updateAssistant(state, action.id, (item) => ({
        ...item,
        tools: item.tools.map((tool) =>
          tool.id === action.callId ? { ...tool, status: action.isError ? "error" : "done" } : tool,
        ),
      }));
    case "card":
      return updateAssistant(state, action.id, (item) => ({
        ...item,
        cards: [...item.cards, action.card],
      }));
    case "proposals":
      return updateAssistant(state, action.id, (item) => ({
        ...item,
        proposals: action.proposals,
      }));
    case "finish":
      return updateAssistant(state, action.id, (item) => ({
        ...item,
        status: item.status === "streaming" ? action.status : item.status,
        error: action.error ?? item.error,
      }));
  }
}
