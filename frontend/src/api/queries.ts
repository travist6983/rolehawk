import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { api, ApiError, unwrap, type Schemas } from "./client";
import type { paths } from "./schema";

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
export type SearchTargetView = Schemas["SearchTargetView"];
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

// --- sources & scrape -----------------------------------------------------------------

export type PortalView = Schemas["PortalView"];
export type CompanyView = Schemas["CompanyView"];
export type CompanyCheck = Schemas["CompanyCheck"];
export type ScrapeSummary = Schemas["ScrapeSummary"];
export type PortalRun = Schemas["PortalRun"];

export const sourceKeys = {
  portals: ["sources", "portals"] as const,
  companies: ["sources", "companies"] as const,
  lastScrape: ["sources", "last-scrape"] as const,
};

export function usePortals() {
  return useQuery({
    queryKey: sourceKeys.portals,
    queryFn: () => unwrap(api.GET("/api/portals")),
  });
}

export function useCompanies() {
  return useQuery({
    queryKey: sourceKeys.companies,
    queryFn: () => unwrap(api.GET("/api/companies")),
  });
}

/** The last successful search's per-source results, or null before the first one. */
export function useLastScrape() {
  return useQuery({
    queryKey: sourceKeys.lastScrape,
    queryFn: async (): Promise<ScrapeSummary | null> => {
      const { data, response } = await api.GET("/api/scrape/last");
      if (!response.ok) throw new ApiError(response.status, "Couldn't load the last search");
      return data ?? null;
    },
  });
}

/** A search or watchlist change moves counts on the cards: refresh everything sources-related. */
export function useInvalidateSources() {
  const client = useQueryClient();
  return useCallback(() => {
    void client.invalidateQueries({ queryKey: ["sources"] });
  }, [client]);
}

function useReplacePortal() {
  const client = useQueryClient();
  return (portal: PortalView) => {
    client.setQueryData<PortalView[]>(sourceKeys.portals, (current) =>
      current?.map((p) => (p.id === portal.id ? portal : p)),
    );
  };
}

export function useSetPortalEnabled() {
  const onSuccess = useReplacePortal();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      unwrap(
        api.PATCH("/api/portals/{portal_id}", {
          params: { path: { portal_id: id } },
          body: { enabled },
        }),
      ),
    onSuccess,
  });
}

export function useSaveCredentials() {
  const onSuccess = useReplacePortal();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & Schemas["CredentialsIn"]) =>
      unwrap(
        api.PUT("/api/portals/{portal_id}/credentials", {
          params: { path: { portal_id: id } },
          body,
        }),
      ),
    onSuccess,
  });
}

export function useClearCredentials() {
  const onSuccess = useReplacePortal();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/api/portals/{portal_id}/credentials", {
          params: { path: { portal_id: id } },
        }),
      ),
    onSuccess,
  });
}

export function useStartScrape() {
  return useMutation({
    mutationFn: (portalIds?: string[]) =>
      unwrap(api.POST("/api/scrape", { body: { portal_ids: portalIds ?? null } })),
  });
}

export function useCheckCompany() {
  return useMutation({
    mutationFn: (body: Schemas["CheckIn"]) => unwrap(api.POST("/api/companies/check", { body })),
  });
}

export function useAddCompanies() {
  const invalidate = useInvalidateSources();
  return useMutation({
    mutationFn: (body: Schemas["CompaniesIn"]) => unwrap(api.POST("/api/companies", { body })),
    onSuccess: invalidate,
  });
}

export function useSetCompanyEnabled() {
  const invalidate = useInvalidateSources();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      unwrap(
        api.PATCH("/api/companies/{company_id}", {
          params: { path: { company_id: id } },
          body: { enabled },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useRemoveCompany() {
  const invalidate = useInvalidateSources();
  return useMutation({
    mutationFn: async (id: number) => {
      const { response } = await api.DELETE("/api/companies/{company_id}", {
        params: { path: { company_id: id } },
      });
      if (!response.ok) throw new ApiError(response.status, "Couldn't remove the company");
    },
    onSuccess: invalidate,
  });
}

// --- jobs & ranking -------------------------------------------------------------------

export type JobRow = Schemas["JobRow"];
export type JobDetail = Schemas["JobDetail"];
export type JobPage = Schemas["JobPage"];
export type JobStats = Schemas["JobStats"];
export type RankPlan = Schemas["RankPlan"];
export type RankParams = Schemas["RankParams"];
export type FilterCounts = Schemas["FilterCounts"];

/** Discover's filters: the /api/jobs query without paging. Empty values are left out. */
export type JobFilters = Omit<
  NonNullable<paths["/api/jobs"]["get"]["parameters"]["query"]>,
  "limit" | "offset"
>;

export const JOB_PAGE_SIZE = 200;

export const jobKeys = {
  all: ["jobs"] as const,
  list: (filters: JobFilters) => ["jobs", "list", filters] as const,
  detail: (id: number) => ["jobs", "detail", id] as const,
  plan: (params: RankParams) => ["jobs", "rank-plan", params] as const,
};

function compact(filters: JobFilters): JobFilters {
  // Empty values are omitted (openapi-fetch drops undefined) rather than sent as "null".
  return {
    ...filters,
    q: filters.q || undefined,
    portal_id: filters.portal_id || undefined,
    min_score: filters.min_score ?? undefined,
  };
}

/** Pages of jobs, loaded as the table scrolls. */
export function useJobs(filters: JobFilters) {
  return useInfiniteQuery({
    queryKey: jobKeys.list(filters),
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/jobs", {
          params: { query: { ...compact(filters), limit: JOB_PAGE_SIZE, offset: pageParam } },
        }),
      ),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((sum, page) => sum + page.items.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
  });
}

export function useJob(id: number | null) {
  return useQuery({
    queryKey: jobKeys.detail(id ?? -1),
    queryFn: () =>
      unwrap(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id ?? -1 } } })),
    enabled: id !== null,
  });
}

/** Fresh every time the dialog opens: counts and spend change between runs. */
export function useRankPlan(params: RankParams, enabled: boolean) {
  return useQuery({
    queryKey: jobKeys.plan(params),
    queryFn: () => unwrap(api.POST("/api/rank/plan", { body: params })),
    enabled,
    staleTime: 0,
    gcTime: 0,
  });
}

export function useInvalidateJobs() {
  const client = useQueryClient();
  return useCallback(() => {
    void client.invalidateQueries({ queryKey: jobKeys.all });
  }, [client]);
}

export function useStartRank() {
  return useMutation({
    mutationFn: (params: RankParams) => unwrap(api.POST("/api/rank", { body: params })),
  });
}

export function useSaveJobs() {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: ({ ids, saved = true }: { ids: number[]; saved?: boolean }) =>
      unwrap(api.POST("/api/jobs/save", { body: { job_ids: ids, saved } })),
    onSuccess: invalidate,
  });
}

export function useDismissJobs() {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: ({ ids, dismissed = true }: { ids: number[]; dismissed?: boolean }) =>
      unwrap(api.POST("/api/jobs/dismiss", { body: { job_ids: ids, dismissed } })),
    onSuccess: invalidate,
  });
}

// --- documents ------------------------------------------------------------------------

export type DocumentSettings = Schemas["DocumentSettingsView"];
export type DocumentTemplate = Schemas["TemplateView"];

export const documentKeys = { settings: ["documents", "settings"] as const };

export function useDocumentSettings() {
  return useQuery({
    queryKey: documentKeys.settings,
    queryFn: () => unwrap(api.GET("/api/documents/settings")),
  });
}

export function useUpdateDocumentSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["DocumentSettingsIn"]) =>
      unwrap(api.PATCH("/api/documents/settings", { body })),
    onSuccess: (view) => {
      client.setQueryData(documentKeys.settings, view);
    },
  });
}

/** Same-origin GET: the session cookie authorizes it, so iframes and download links work. */
export function templatePreviewUrl(id: string, format: "pdf" | "docx" = "pdf"): string {
  const query = format === "pdf" ? "" : "?format=docx";
  return `/api/templates/${encodeURIComponent(id)}/preview${query}`;
}

// --- applications ---------------------------------------------------------------------

export type ApplyPlan = Schemas["ApplyPlan"];
export type ApplicationDetail = Schemas["ApplicationDetail"];
export type Bundle = Schemas["Bundle"];
export type Flag = Schemas["Flag"];
export type CvDocument = Schemas["CvDocument-Output"];
export type CoverLetter = Schemas["CoverLetter-Output"];
export type Stage = Schemas["Stage"];
export type AutofillReport = Schemas["AutofillReport"];
export type RegenerateSection = Schemas["RegenerateIn"]["section"];

export const applicationKeys = {
  detail: (id: number) => ["applications", id] as const,
  plan: (jobId: number) => ["applications", "plan", jobId] as const,
};

export function useApplyPlan(jobId: number | null) {
  return useQuery({
    queryKey: applicationKeys.plan(jobId ?? -1),
    queryFn: () => unwrap(api.POST("/api/apply/plan", { body: { job_id: jobId ?? -1 } })),
    enabled: jobId !== null,
    staleTime: 0,
  });
}

export function useStartApply() {
  return useMutation({
    mutationFn: (body: Schemas["ApplyParams"]) => unwrap(api.POST("/api/apply", { body })),
  });
}

export function useApplication(id: number) {
  return useQuery({
    queryKey: applicationKeys.detail(id),
    queryFn: () =>
      unwrap(
        api.GET("/api/applications/{application_id}", {
          params: { path: { application_id: id } },
        }),
      ),
  });
}

function useSetApplication(id: number) {
  const client = useQueryClient();
  return (detail: ApplicationDetail) => {
    client.setQueryData(applicationKeys.detail(id), detail);
    void client.invalidateQueries({ queryKey: jobKeys.all });
  };
}

export function useUpdateApplication(id: number) {
  const onSuccess = useSetApplication(id);
  return useMutation({
    mutationFn: (body: Schemas["StagePatch"]) =>
      unwrap(
        api.PATCH("/api/applications/{application_id}", {
          params: { path: { application_id: id } },
          body,
        }),
      ),
    onSuccess,
  });
}

export function useSaveDocuments(id: number) {
  const onSuccess = useSetApplication(id);
  return useMutation({
    mutationFn: (body: Schemas["DocumentsIn"]) =>
      unwrap(
        api.PUT("/api/applications/{application_id}/documents", {
          params: { path: { application_id: id } },
          body,
        }),
      ),
    onSuccess,
  });
}

export function useRegenerate(id: number) {
  return useMutation({
    mutationFn: (body: Schemas["RegenerateIn"]) =>
      unwrap(
        api.POST("/api/applications/{application_id}/regenerate", {
          params: { path: { application_id: id } },
          body,
        }),
      ),
  });
}

export function useAutofill(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/applications/{application_id}/autofill", {
          params: { path: { application_id: id } },
        }),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: applicationKeys.detail(id) });
    },
  });
}

/** Same-origin GET (the session cookie authorizes it): for iframes and download links. */
export function applicationFileUrl(
  id: number,
  document: "cv" | "cover_letter",
  format: "pdf" | "docx",
  version?: string,
): string {
  const query = version ? `?v=${encodeURIComponent(version)}` : "";
  return `/api/applications/${String(id)}/files/${document}.${format}${query}`;
}

// --- pipeline, insights, reports, reset -----------------------------------------------

export type Board = Schemas["Board"];
export type BoardColumn = Schemas["Column"];
export type BoardCard = Schemas["Card"];
export type Insights = Schemas["Insights"];
export type ResetScopeView = Schemas["ScopeView"];
export type ResetResult = Schemas["ResetResult"];

export const pipelineKeys = {
  board: ["pipeline"] as const,
  insights: ["insights"] as const,
  resetScopes: ["reset", "scopes"] as const,
};

export function usePipeline() {
  return useQuery({
    queryKey: pipelineKeys.board,
    queryFn: () => unwrap(api.GET("/api/pipeline")),
  });
}

/** Optimistic: the card moves at once; the server records the stage event. */
export function useMoveApplication() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, stage }: { id: number; stage: Stage }) =>
      unwrap(
        api.PATCH("/api/applications/{application_id}", {
          params: { path: { application_id: id } },
          body: { stage },
        }),
      ),
    onMutate: async ({ id, stage }) => {
      await client.cancelQueries({ queryKey: pipelineKeys.board });
      const previous = client.getQueryData<Board>(pipelineKeys.board);
      if (previous) client.setQueryData(pipelineKeys.board, moveCard(previous, id, stage));
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) client.setQueryData(pipelineKeys.board, context.previous);
    },
    onSettled: (_data, _error, { id }) => {
      void client.invalidateQueries({ queryKey: pipelineKeys.board });
      void client.invalidateQueries({ queryKey: pipelineKeys.insights });
      void client.invalidateQueries({ queryKey: applicationKeys.detail(id) });
    },
  });
}

export function moveCard(board: Board, id: number, stage: Stage): Board {
  const card = board.columns.flatMap((c) => c.cards).find((c) => c.application_id === id);
  if (!card) return board;
  const moved = { ...card, stage, days_in_stage: 0 };
  return {
    ...board,
    columns: board.columns.map((column) => {
      const without = column.cards.filter((c) => c.application_id !== id);
      return column.stages.includes(stage)
        ? { ...column, cards: [moved, ...without] }
        : { ...column, cards: without };
    }),
  };
}

export function useInsights() {
  return useQuery({
    queryKey: pipelineKeys.insights,
    queryFn: () => unwrap(api.GET("/api/insights")),
  });
}

export function useCreateReport() {
  return useMutation({ mutationFn: () => unwrap(api.POST("/api/reports")) });
}

export function reportUrl(filename: string): string {
  return `/api/reports/${encodeURIComponent(filename)}`;
}

export function useResetScopes() {
  return useQuery({
    queryKey: pipelineKeys.resetScopes,
    queryFn: () => unwrap(api.GET("/api/reset/scopes")),
    staleTime: Infinity,
  });
}

export function useReset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["ResetIn"]) => unwrap(api.POST("/api/reset", { body })),
    onSuccess: () => {
      void client.invalidateQueries(); // everything may have changed
    },
  });
}

// --- /add-portal ----------------------------------------------------------------------

export type Inspection = Schemas["Inspection"];
export type PortalCandidate = Schemas["Candidate"];
export type PortalTestResult = Schemas["TestResult"];
export type PortalDefinition = NonNullable<PortalCandidate["definition"]>;

export function useInspectPortal() {
  return useMutation({
    mutationFn: (url: string) => unwrap(api.POST("/api/portals/inspect", { body: { url } })),
  });
}

export function useDraftPortal() {
  return useMutation({
    mutationFn: ({ url, name }: { url: string; name?: string }) =>
      unwrap(api.POST("/api/portals/draft", { body: { url, name: name ?? null } })),
  });
}

export function useTestPortal() {
  return useMutation({
    mutationFn: (definition: PortalDefinition) =>
      unwrap(api.POST("/api/portals/test", { body: { definition } })),
  });
}

export function useAddCustomPortal() {
  const invalidate = useInvalidateSources();
  return useMutation({
    mutationFn: (definition: PortalDefinition) =>
      unwrap(api.POST("/api/portals/custom", { body: { definition } })),
    onSuccess: invalidate,
  });
}

export function useRemoveCustomPortal() {
  const invalidate = useInvalidateSources();
  return useMutation({
    mutationFn: async (definitionId: string) => {
      const { response } = await api.DELETE("/api/portals/custom/{definition_id}", {
        params: { path: { definition_id: definitionId } },
      });
      if (!response.ok) throw new ApiError(response.status, "Couldn't remove the source");
    },
    onSuccess: invalidate,
  });
}
