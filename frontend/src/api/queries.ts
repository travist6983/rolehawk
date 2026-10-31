import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap, type Schemas } from "./client";

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

// --- profile & setup ------------------------------------------------------------------

export type ProfileOverview = Schemas["ProfileOverview"];
// Responses use the "-Output" variants (every field present); request bodies the "-Input" ones.
export type Profile = Schemas["Profile-Output"];
export type Preferences = Schemas["Preferences-Output"];
export type InterviewState = Schemas["InterviewState"];
export type Question = Schemas["Question"];
export type DocumentView = Schemas["DocumentView"];
export type Draft = Schemas["Draft"];
export type ApplyResult = Schemas["ApplyResult"];
export type AnswerValue = Schemas["AnswerIn"]["value"];

export const setupKeys = {
  profile: ["profile"] as const,
  interview: ["setup", "interview"] as const,
  documents: ["setup", "documents"] as const,
  draft: ["setup", "draft"] as const,
};

export function useProfileOverview() {
  return useQuery({ queryKey: setupKeys.profile, queryFn: () => unwrap(api.GET("/api/profile")) });
}

export function useInterview() {
  return useQuery({
    queryKey: setupKeys.interview,
    queryFn: () => unwrap(api.GET("/api/setup/interview")),
  });
}

export function useDocuments() {
  return useQuery({
    queryKey: setupKeys.documents,
    queryFn: () => unwrap(api.GET("/api/setup/documents")),
  });
}

/** The pending draft, or null when there is none (404). */
export function useDraft() {
  return useQuery({
    queryKey: setupKeys.draft,
    queryFn: async (): Promise<Draft | null> => {
      const { data, response } = await api.GET("/api/setup/draft");
      if (response.status === 404) return null;
      if (!data) throw new ApiError(response.status, "Couldn't load the draft");
      return data;
    },
  });
}

/** Profile files changed: refresh everything derived from them. */
function useInvalidateProfile({ interview = true }: { interview?: boolean } = {}) {
  const client = useQueryClient();
  return () => {
    const keys = [setupKeys.profile, queryKeys.memory, ...(interview ? [setupKeys.interview] : [])];
    for (const key of keys) void client.invalidateQueries({ queryKey: key });
  };
}

export function useUploadDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) =>
      unwrap(
        api.POST("/api/setup/documents", {
          // OpenAPI models binary uploads as strings; the serializer sends the real File.
          body: { file: file as unknown as string },
          bodySerializer: () => {
            const form = new FormData();
            form.append("file", file, file.name); // explicit name survives every runtime
            return form;
          },
        }),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: setupKeys.documents });
    },
  });
}

export function usePasteText() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => unwrap(api.POST("/api/setup/documents/text", { body: { text } })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: setupKeys.documents });
    },
  });
}

export function useStartExtraction() {
  return useMutation({
    mutationFn: (documentIds: number[]) =>
      unwrap(api.POST("/api/setup/extract", { body: { document_ids: documentIds } })),
  });
}

export function useApplyDraft() {
  const client = useQueryClient();
  const invalidate = useInvalidateProfile();
  return useMutation({
    mutationFn: (edited: Schemas["ExtractedSetup"]) =>
      unwrap(api.POST("/api/setup/draft/apply", { body: edited })),
    onSuccess: () => {
      client.setQueryData(setupKeys.draft, null);
      invalidate();
    },
  });
}

export function useDiscardDraft() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { response } = await api.DELETE("/api/setup/draft");
      if (!response.ok) throw new ApiError(response.status, "Couldn't discard the draft");
    },
    onSuccess: () => {
      client.setQueryData(setupKeys.draft, null);
    },
  });
}

export function useAnswer() {
  const client = useQueryClient();
  const invalidate = useInvalidateProfile({ interview: false }); // the answer returns it
  return useMutation({
    mutationFn: ({ questionId, value }: { questionId: string; value: AnswerValue }) =>
      unwrap(api.POST("/api/setup/interview/answer", { body: { question_id: questionId, value } })),
    onSuccess: (state) => {
      client.setQueryData(setupKeys.interview, state);
      invalidate();
    },
  });
}

export function useSkipQuestion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (questionId: string) =>
      unwrap(api.POST("/api/setup/interview/skip", { body: { question_id: questionId } })),
    onSuccess: (state) => {
      client.setQueryData(setupKeys.interview, state);
    },
  });
}

export function useSaveMemoryFile() {
  const invalidate = useInvalidateProfile();
  return useMutation({
    mutationFn: ({
      target,
      markdown,
    }: {
      target: "profile" | "preferences" | "facts";
      markdown: string;
    }) =>
      unwrap(api.PUT("/api/memory/{target}", { params: { path: { target } }, body: { markdown } })),
    onSuccess: invalidate,
  });
}
