import type {
  ApplicationDetail,
  ApplyPlan,
  Board,
  BoardCard,
  Bundle,
  Insights,
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
  KeyConnect,
  KeyTest,
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
  typical_cost: {
    active: {
      jobs_ranked_per_week: 200,
      applications_per_week: 10,
      chat_messages_per_week: 20,
      monthly_usd: 18.14,
    },
    light: {
      jobs_ranked_per_week: 50,
      applications_per_week: 2,
      chat_messages_per_week: 5,
      monthly_usd: 3.87,
    },
    writing_model: "Claude Opus 5.5",
    ranking_model: "Claude Haiku 5.5",
  },
  ...overrides,
});

export const keyTest = (overrides: Partial<KeyTest> = {}): KeyTest => ({
  ok: true,
  problem: null,
  key_accepted: true,
  title: "Your key works",
  fix: "Claude answered a test message, so ranking jobs and writing applications are ready.",
  fix_link: null,
  ...overrides,
});

export const noCredit = (): KeyTest =>
  keyTest({
    ok: false,
    problem: "no_credit",
    title: "Your key works, but the account has no credit",
    fix: "Open Billing and buy some credit, then test again.",
    fix_link: "billing",
  });

export const badKey = (): KeyTest =>
  keyTest({
    ok: false,
    problem: "bad_key",
    key_accepted: false,
    title: "Anthropic didn't accept this key",
    fix: "Check you copied the whole key, starting with sk-ant-.",
    fix_link: "keys",
  });

export const keyConnect = (test: KeyTest = keyTest()): KeyConnect => ({
  saved: test.key_accepted,
  test,
  status: llmStatus(test.key_accepted ? {} : { configured: false, key_source: "none" }),
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
  energizing: [],
  draining: [],
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
  can_go_back: false,
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
  custom: false,
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
    enabled: false,
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
    enabled: false,
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
  breakdown: { experience: 90, skills: 80, career: 85, logistics: 90 },
  gates: {
    eligibility: { verdict: "pass", quote: "" },
    language: { verdict: "pass", quote: "" },
    deal_breaker: "",
  },
  stage: null,
  dismissed: false,
  closes_at: null,
  deadline: null,
  stale_days: null,
  integrity: "clean",
  ...overrides,
});

export const jobDetail = (overrides: Partial<JobDetail> = {}): JobDetail => ({
  ...jobRow(),
  description: "About the role\n\nYou'll own reporting for our finance team.",
  application_id: null,
  integrity_report: null,
  ...overrides,
});

export const jobStats = (overrides: Partial<JobStats> = {}): JobStats => ({
  jobs: 0,
  ranked: 0,
  unranked: 0,
  saved: 0,
  dismissed: 0,
  closed: 0,
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
    closed: 0,
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

// --- applications -------------------------------------------------------------------------

export const applyPlan = (overrides: Partial<ApplyPlan> = {}): ApplyPlan => ({
  job_id: 1,
  fit: {
    score: 86,
    reasons: ["Your SQL and Looker work matches their stack"],
    must_have_gaps: ["dbt"],
    threshold: 60,
    passes: true,
    gates: null,
  },
  threshold: 60,
  application_id: null,
  has_documents: false,
  has_profile: true,
  configured: true,
  estimated_cost_usd: 0.14,
  ...overrides,
});

const contact = {
  name: "Ada Example",
  email: "ada@example.com",
  phone: null,
  location: "Austin, TX",
  links: [],
};

export const bundle = (overrides: Partial<Bundle> = {}): Bundle => ({
  version: 1,
  job_id: 1,
  cv: {
    contact,
    headline: "Senior Data Analyst",
    summary: "Analyst who grew signups 300%.",
    experience: [
      {
        title: "Data Analyst",
        organization: "Northwind",
        location: null,
        start: "2021-03",
        end: null,
        current: true,
        bullets: ["Built the revenue dashboard", "Cut reporting time in half"],
      },
    ],
    education: [],
    skills: ["SQL", "Looker"],
    projects: [],
    certifications: [],
    achievements: [],
    languages: [],
    section_order: [
      "summary",
      "experience",
      "education",
      "skills",
      "projects",
      "certifications",
      "achievements",
      "languages",
    ],
  },
  cover_letter: {
    contact,
    date: "31 October 2026",
    recipient: { company: "Globex", name: null, address_lines: [] },
    greeting: "Dear Globex team,",
    paragraphs: ["First paragraph.", "Second paragraph."],
    closing: "Sincerely,",
    signature: null,
  },
  cv_template: "classic",
  cover_template: "classic-letter",
  flags: [
    {
      document: "cv",
      location: "summary",
      text: "Analyst who grew signups 300%.",
      issue: "300% isn't in your profile",
      source: "check",
      kind: "unsupported",
    },
  ],
  fit: applyPlan().fit,
  model: "claude-opus-5-5",
  files: {
    cv: { pdf: "/data/7/ada-example-cv.pdf", docx: "/data/7/ada-example-cv.docx" },
    cover_letter: { pdf: "/data/7/ada-example-cover-letter.pdf" },
  },
  pdf_unavailable: false,
  requirements: [
    {
      requirement: "SQL",
      priority: "required",
      terms: ["SQL"],
      also: [],
      keyword: "covered",
      matched: "SQL",
      addressed: true,
      note: "Shown in the Northwind role.",
    },
    {
      requirement: "dbt",
      priority: "required",
      terms: ["dbt"],
      also: ["data build tool"],
      keyword: "gap",
      matched: null,
      addressed: false,
      note: "Neither document mentions dbt.",
    },
  ],
  ats: {
    source: "pdf",
    checks: [
      { name: "Readable text", passed: true, detail: "The text layer extracts cleanly." },
      {
        name: "Plain hyphens in dates",
        passed: false,
        detail: "Dates joined by a typographic dash can be dropped on import: 2021 – 2023",
      },
    ],
  },
  kept: [],
  updated_at: "2026-10-31T12:00:00Z",
  ...overrides,
});

export const applicationDetail = (
  overrides: Partial<ApplicationDetail> = {},
): ApplicationDetail => ({
  id: 7,
  stage: "applying",
  method: null,
  applied_at: null,
  stage_changed_at: "2026-10-31T12:00:00Z",
  notes: null,
  job: { ...jobDetail(), application_id: 7, stage: "applying" },
  documents: bundle(),
  history: [
    {
      from_stage: null,
      to_stage: "applying",
      source: "user",
      created_at: "2026-10-31T12:00:00Z",
    },
  ],
  ...overrides,
});

// --- pipeline & insights ------------------------------------------------------------------

export const boardCard = (overrides: Partial<BoardCard> = {}): BoardCard => ({
  application_id: 7,
  job_id: 1,
  title: "Senior Data Analyst",
  company: "Northwind",
  location: "Denver, CO",
  source: "Greenhouse",
  stage: "applying",
  score: 86,
  days_in_stage: 3,
  applied_at: null,
  has_documents: true,
  flags: 0,
  closes_at: null,
  follow_ups: 0,
  follow_up_due: false,
  next_action: "Submit, then mark as applied",
  ...overrides,
});

const COLUMNS: [string, string, BoardCard["stage"][]][] = [
  ["saved", "Saved", ["saved"]],
  ["applying", "Applying", ["applying"]],
  ["applied", "Applied", ["applied"]],
  ["screen", "Screen", ["screen"]],
  ["interview", "Interview", ["interview"]],
  ["offer", "Offer", ["offer"]],
  ["closed", "Closed", ["rejected", "withdrawn", "ghosted"]],
];

export const board = (cards: BoardCard[] = []): Board => ({
  columns: COLUMNS.map(([id, label, stages]) => ({
    id,
    label,
    stages,
    cards: cards.filter((c) => stages.includes(c.stage)),
  })),
  total: cards.length,
});

export const insights = (overrides: Partial<Insights> = {}): Insights => ({
  generated_at: "2026-10-31T12:00:00Z",
  totals: {
    jobs: 2524,
    applications: 5,
    active: 4,
    applied: 3,
    responses: 2,
    response_rate: 2 / 3,
    interviews: 1,
    offers: 0,
  },
  funnel: [
    { stage: "saved", label: "Saved", count: 5, rate_from_previous: null },
    { stage: "applying", label: "Applying", count: 4, rate_from_previous: 0.8 },
    { stage: "applied", label: "Applied", count: 3, rate_from_previous: 0.75 },
    { stage: "screen", label: "Screen", count: 2, rate_from_previous: 2 / 3 },
    { stage: "interview", label: "Interview", count: 1, rate_from_previous: 0.5 },
    { stage: "offer", label: "Offer", count: 0, rate_from_previous: 0 },
  ],
  by_source: [
    { source: "Greenhouse", applied: 2, responses: 2, rate: 1 },
    { source: "Lever", applied: 1, responses: 0, rate: 0 },
  ],
  weekly: [
    { week_start: "2026-10-19", applied: 1, jobs_found: 400 },
    { week_start: "2026-10-26", applied: 2, jobs_found: 2124 },
  ],
  spend: {
    month_to_date_usd: 1.5,
    cap_usd: 20,
    by_command: [{ command: "apply", cost_usd: 1.2, calls: 6 }],
  },
  ...overrides,
});
