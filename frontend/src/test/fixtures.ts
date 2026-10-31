import type {
  CommandInfo,
  CompanyView,
  DocumentSettings,
  JobDetail,
  JobPage,
  JobRow,
  JobStats,
  RankPlan,
  InterviewState,
  LLMStatus,
  MemorySnapshot,
  PortalRun,
  PortalView,
  Preferences,
  Profile,
  ProfileOverview,
  ProposalView,
  Question,
  ScrapeSummary,
  SearchTargetView,
  TaskView,
} from "@/api/queries";

export const TEST_TOKEN = "test-token";

export const llmStatus = (overrides: Partial<LLMStatus> = {}): LLMStatus => ({
  configured: true,
  key_source: "keychain",
  provider: "anthropic_api",
  model: "claude-opus-5-5",
  smart_routing: true,
  routes: [
    { task: "rank", model: "claude-haiku-5-5", effort: "low" },
    { task: "extract", model: "claude-haiku-5-5", effort: "low" },
    { task: "write", model: "claude-opus-5-5", effort: "high" },
    { task: "review", model: "claude-opus-5-5", effort: "high" },
    { task: "chat", model: "claude-opus-5-5", effort: "medium" },
  ],
  monthly_cap_usd: null,
  month_to_date_usd: 1.25,
  ...overrides,
});

export const commands: CommandInfo[] = [
  {
    name: "setup-import",
    description: "Import a resume from a local file path.",
    read_only: false,
    background: false,
    release: "v1.0",
    chat_allowed: false,
    params_schema: {},
  },
  {
    name: "context",
    description: "Export the context pack.",
    read_only: true,
    background: false,
    release: "v1.0",
    chat_allowed: true,
    params_schema: {},
  },
  {
    name: "memory",
    description: "Show memory files and pending proposals.",
    read_only: true,
    background: false,
    release: "v1.0",
    chat_allowed: true,
    params_schema: {},
  },
  {
    name: "propose",
    description: "Propose a memory edit.",
    read_only: false,
    background: false,
    release: "v1.0",
    chat_allowed: true,
    params_schema: {},
  },
  {
    name: "selftest",
    description: "Run a short background task.",
    read_only: true,
    background: true,
    release: "v1.0",
    chat_allowed: true,
    params_schema: {},
  },
  {
    name: "spend",
    description: "Show AI spend this month and the cap.",
    read_only: true,
    background: false,
    release: "v1.0",
    chat_allowed: true,
    params_schema: {},
  },
];

export const memory = (overrides: Partial<MemorySnapshot> = {}): MemorySnapshot => ({
  profile: "# Profile\n\n## Experience\n\n- Senior Engineer at Acme (2020-2024)\n",
  preferences: "# Preferences\n\n## Remote\n\n- Remote only\n",
  facts: "# Facts\n",
  latest_session: null,
  ...overrides,
});

export const proposal = (overrides: Partial<ProposalView> = {}): ProposalView => ({
  id: 7,
  target: "facts",
  op: "add",
  section: null,
  text: "Prefers async-first teams",
  old_text: null,
  reason: "You said so in chat",
  source: "chat",
  session_id: "s1",
  status: "pending",
  created_at: "2026-10-31T12:00:00Z",
  resolved_at: null,
  ...overrides,
});

export const task = (overrides: Partial<TaskView> = {}): TaskView => ({
  id: "t1",
  kind: "selftest",
  status: "running",
  progress: 0.4,
  message: "Step 2 of 5",
  params: {},
  result: null,
  error: null,
  created_at: "2026-10-31T12:00:00Z",
  started_at: "2026-10-31T12:00:01Z",
  finished_at: null,
  ...overrides,
});

export const emptyProfile = (): Profile => ({
  contact: { name: null, email: null, phone: null, location: null, links: [] },
  headline: null,
  summary: null,
  experience: [],
  education: [],
  skills: [],
  projects: [],
  certifications: [],
  achievements: [],
  languages: [],
});

export const emptyPreferences = (): Preferences => ({
  target_titles: [],
  seniority: null,
  locations: [],
  remote: null,
  country: null,
  salary_floor: null,
  work_authorization: null,
  deal_breakers: [],
});

export const sampleProfile = (): Profile => ({
  ...emptyProfile(),
  contact: {
    name: "Ada Example",
    email: "ada@example.com",
    phone: null,
    location: "Austin, TX",
    links: [],
  },
  headline: "Senior Frontend Engineer",
  experience: [
    {
      title: "Senior Frontend Engineer",
      company: "Northwind Payments",
      location: "Remote",
      start: "2021-03",
      end: null,
      current: true,
      highlights: ["Led the checkout redesign, lifting conversion 12%"],
    },
  ],
  skills: ["TypeScript", "React", "Accessibility"],
});

export const profileOverview = (overrides: Partial<ProfileOverview> = {}): ProfileOverview => ({
  profile: emptyProfile(),
  preferences: emptyPreferences(),
  completeness: { score: 0, missing: ["name", "experience"] },
  search_targets: [],
  ...overrides,
});

export const question = (overrides: Partial<Question> = {}): Question => ({
  id: "prefs.remote",
  prompt: "How do you want to work?",
  help: null,
  kind: "single",
  choices: [
    { value: "remote", label: "Remote only" },
    { value: "hybrid", label: "Hybrid" },
  ],
  allow_other: false,
  optional: false,
  skip_label: "Skip",
  placeholder: null,
  fields: [],
  value: null,
  ...overrides,
});

export const interviewState = (overrides: Partial<InterviewState> = {}): InterviewState => ({
  question: question(),
  answered: 2,
  remaining: 6,
  complete: false,
  ...overrides,
});

// --- sources ------------------------------------------------------------------------------

export const portal = (overrides: Partial<PortalView> = {}): PortalView => ({
  id: "greenhouse",
  name: "Greenhouse",
  kind: "ats",
  risk_level: "low",
  countries: ["*"],
  enabled: true,
  ready: true,
  missing: [],
  secret_fields: [],
  config_fields: [],
  config: {},
  status: null,
  last_run_at: null,
  last_error: null,
  jobs_found: 0,
  companies: 59,
  docs_url: "https://developers.greenhouse.io/job-board.html",
  ...overrides,
});

/** The eight built-in sources on a fresh install: ATS boards ready, keyed feeds not. */
export const portals = (): PortalView[] => [
  portal(),
  portal({ id: "lever", name: "Lever", companies: 16 }),
  portal({ id: "ashby", name: "Ashby", companies: 33 }),
  portal({ id: "workable", name: "Workable", companies: 6 }),
  portal({ id: "remoteok", name: "Remote OK", kind: "feed", companies: null }),
  portal({ id: "weworkremotely", name: "We Work Remotely", kind: "feed", companies: null }),
  portal({
    id: "adzuna",
    name: "Adzuna",
    kind: "feed",
    companies: null,
    countries: ["GB", "US", "DE"],
    ready: false,
    missing: ["an app ID", "an app key"],
    secret_fields: ["app_id", "app_key"],
    docs_url: "https://developer.adzuna.com/docs/search",
  }),
  portal({
    id: "usajobs",
    name: "USAJOBS",
    kind: "feed",
    companies: null,
    countries: ["US"],
    ready: false,
    missing: ["an API key", "your email"],
    secret_fields: ["api_key"],
    config_fields: ["email"],
    docs_url: "https://developer.usajobs.gov/api-reference/get-api-search",
  }),
];

export const company = (overrides: Partial<CompanyView> = {}): CompanyView => ({
  id: 1,
  ats: "greenhouse",
  slug: "airbnb",
  name: "Airbnb",
  industry: "Travel",
  country: "US",
  source: "starter",
  enabled: true,
  last_job_count: null,
  last_error: null,
  ...overrides,
});

export const portalRun = (overrides: Partial<PortalRun> = {}): PortalRun => ({
  portal_id: "greenhouse",
  name: "Greenhouse",
  status: "ok",
  found: 1200,
  matched: 40,
  new: 12,
  duplicates: 28,
  errors: [],
  detail: null,
  ...overrides,
});

export const scrapeSummary = (overrides: Partial<ScrapeSummary> = {}): ScrapeSummary => ({
  started_at: "2026-10-31T11:59:00Z",
  finished_at: "2026-10-31T12:00:00Z",
  queries: ["Data Analyst"],
  portals: [portalRun()],
  found: 1200,
  new: 12,
  duplicates: 28,
  ...overrides,
});

export const searchTarget = (overrides: Partial<SearchTargetView> = {}): SearchTargetView => ({
  id: 1,
  title: "Data Analyst",
  seniority: null,
  locations: [],
  remote_policy: "any",
  country: "US",
  salary_min: null,
  active: true,
  ...overrides,
});

// --- jobs ---------------------------------------------------------------------------------

export const jobRow = (overrides: Partial<JobRow> = {}): JobRow => ({
  id: 1,
  title: "Senior Data Analyst",
  company: "Northwind",
  location: "Denver, CO",
  remote: null,
  salary_text: "$120K - $150K",
  portal_id: "greenhouse",
  source: "Greenhouse",
  url: "https://boards.greenhouse.io/northwind/jobs/1",
  posted_at: "2026-10-30T12:00:00Z",
  scraped_at: "2026-10-31T09:00:00Z",
  score: 86,
  reasons: ["Your SQL and Looker work matches their stack", "Hybrid in Denver"],
  must_have_gaps: ["dbt"],
  scored_at: "2026-10-31T10:00:00Z",
  score_model: "claude-haiku-5-5",
  stage: null,
  dismissed: false,
  ...overrides,
});

export const jobDetail = (overrides: Partial<JobDetail> = {}): JobDetail => ({
  ...jobRow(),
  description: "About the role\n\nYou'll own reporting for our finance team.",
  application_id: null,
  ...overrides,
});

export const jobStats = (overrides: Partial<JobStats> = {}): JobStats => ({
  jobs: 0,
  ranked: 0,
  unranked: 0,
  saved: 0,
  dismissed: 0,
  ...overrides,
});

export const jobPage = (items: JobRow[], stats: Partial<JobStats> = {}): JobPage => ({
  items,
  total: items.length,
  stats: jobStats({ jobs: items.length, ...stats }),
});

export const rankPlan = (overrides: Partial<RankPlan> = {}): RankPlan => ({
  candidates: 42,
  remaining: 0,
  filtered: {
    already_ranked: 0,
    applied: 0,
    dismissed: 0,
    country: 5,
    location: 8,
    salary: 3,
    excluded: 0,
  },
  batches: 3,
  model: "claude-haiku-5-5",
  estimated_cost_usd: 0.21,
  month_to_date_usd: 1.5,
  cap_usd: 20,
  exceeds_cap: false,
  configured: true,
  ...overrides,
});

// --- documents ----------------------------------------------------------------------------

export const documentSettings = (overrides: Partial<DocumentSettings> = {}): DocumentSettings => ({
  cv_template: "classic",
  cover_template: "classic-letter",
  paper: "letter",
  paper_auto: true,
  templates: [
    { id: "classic", name: "Classic", kind: "cv", description: "Serif type.", selected: true },
    { id: "modern", name: "Modern", kind: "cv", description: "Indigo accent.", selected: false },
    { id: "compact", name: "Compact", kind: "cv", description: "Tighter.", selected: false },
    {
      id: "classic-letter",
      name: "Classic letter",
      kind: "cover_letter",
      description: "Block letter.",
      selected: true,
    },
    {
      id: "modern-letter",
      name: "Modern letter",
      kind: "cover_letter",
      description: "Sans-serif.",
      selected: false,
    },
  ],
  ...overrides,
});
