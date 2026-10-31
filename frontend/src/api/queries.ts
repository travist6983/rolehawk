import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "./client";

export type LLMStatus = Schemas["LLMStatus"];
export type TaskView = Schemas["TaskView"];
export type CommandInfo = Schemas["CommandInfo"];
export type ProposalView = Schemas["ProposalView"];
export type MemorySnapshot = Schemas["MemorySnapshot"];
export type ModelChoice = Schemas["ModelChoice"];
export type ChatMessageView = Schemas["ChatMessageView"];

export const queryKeys = {
  session: ["session"] as const,
  llmStatus: ["llm", "status"] as const,
  models: ["llm", "models"] as const,
  commands: ["commands"] as const,
  memory: ["memory"] as const,
  proposals: ["memory", "proposals"] as const,
  tasks: ["tasks"] as const,
  chatMessages: (sessionId: string) => ["chat", sessionId, "messages"] as const,
};

export function useSessionInfo() {
  return useQuery({
    queryKey: queryKeys.session,
    queryFn: () => unwrap(api.GET("/api/session")),
    staleTime: Infinity,
  });
}

export function useLLMStatus() {
  return useQuery({
    queryKey: queryKeys.llmStatus,
    queryFn: () => unwrap(api.GET("/api/llm/status")),
  });
}

export function useModels(enabled = true) {
  return useQuery({
    queryKey: queryKeys.models,
    queryFn: () => unwrap(api.GET("/api/llm/models")),
    staleTime: 10 * 60_000,
    enabled,
  });
}

export function useCommands() {
  return useQuery({
    queryKey: queryKeys.commands,
    queryFn: () => unwrap(api.GET("/api/commands")),
    staleTime: Infinity,
  });
}

export function useMemory() {
  return useQuery({ queryKey: queryKeys.memory, queryFn: () => unwrap(api.GET("/api/memory")) });
}

export function useProposals() {
  return useQuery({
    queryKey: queryKeys.proposals,
    queryFn: () => unwrap(api.GET("/api/memory/proposals")),
  });
}

export function useRecentTasks() {
  return useQuery({
    queryKey: queryKeys.tasks,
    queryFn: () => unwrap(api.GET("/api/tasks", { params: { query: { limit: 20 } } })),
  });
}

function useInvalidateLLM() {
  const client = useQueryClient();
  return (status: LLMStatus) => {
    client.setQueryData(queryKeys.llmStatus, status);
    void client.invalidateQueries({ queryKey: queryKeys.models });
  };
}

export function useSetApiKey() {
  const onSuccess = useInvalidateLLM();
  return useMutation({
    mutationFn: (apiKey: string) => unwrap(api.PUT("/api/llm/key", { body: { api_key: apiKey } })),
    onSuccess,
  });
}

export function useClearApiKey() {
  const onSuccess = useInvalidateLLM();
  return useMutation({ mutationFn: () => unwrap(api.DELETE("/api/llm/key")), onSuccess });
}

export function useUpdateLLMSettings() {
  const onSuccess = useInvalidateLLM();
  return useMutation({
    mutationFn: (body: Schemas["LLMSettingsIn"]) =>
      unwrap(api.PATCH("/api/llm/settings", { body })),
    onSuccess,
  });
}

export function useResolveProposal() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: "accept" | "reject" }) =>
      action === "accept"
        ? unwrap(
            api.POST("/api/memory/proposals/{proposal_id}/accept", {
              params: { path: { proposal_id: id } },
            }),
          )
        : unwrap(
            api.POST("/api/memory/proposals/{proposal_id}/reject", {
              params: { path: { proposal_id: id } },
            }),
          ),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.memory });
    },
  });
}

export function useRunCommand() {
  return useMutation({
    mutationFn: ({ name, params }: { name: string; params?: Record<string, unknown> }) =>
      unwrap(
        api.POST("/api/commands/{name}", {
          params: { path: { name } },
          body: { params: params ?? {} },
        }),
      ),
  });
}
