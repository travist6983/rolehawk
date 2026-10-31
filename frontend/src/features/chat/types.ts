import type { ProposalView, TaskView } from "@/api/queries";

/** Cards the backend (or a slash command) attaches to an assistant message. Unknown types
 *  still render through the registry's fallback, so the backend can ship new cards first. */
export type ChatCard =
  | { type: "memory_proposal"; proposal: ProposalView }
  | {
      type: "command_proposal";
      command: string;
      params: Record<string, unknown>;
      description: string;
    }
  | { type: "task"; task_id: string; command: string }
  | { type: "command_result"; command: string; result: unknown }
  | {
      type: "job";
      job_id: number;
      company: string;
      title: string;
      location?: string | null;
      score?: number | null;
      url?: string | null;
    }
  | {
      type: "document";
      application_id: number;
      label: string;
      files: { name: string; path: string }[];
    }
  | {
      type: "stage_proposal";
      application_id: number;
      company: string;
      from_stage: string | null;
      to_stage: string;
      evidence?: string | null;
    }
  | { type: string; [key: string]: unknown };

export interface ToolActivity {
  id: string;
  name: string;
  status: "running" | "done" | "error";
}

export type AssistantStatus = "streaming" | "done" | "error" | "stopped";

export type ChatItem =
  | { kind: "user"; id: string; text: string }
  | {
      kind: "assistant";
      id: string;
      text: string;
      cards: ChatCard[];
      tools: ToolActivity[];
      proposals: ProposalView[];
      status: AssistantStatus;
      error?: string;
    };

/** What the user is looking at, sent with each message and shown as the context chip. */
export interface ChatView {
  label: string;
  route: string;
  job_ids?: number[];
  application_ids?: number[];
}

export type { ProposalView, TaskView };
