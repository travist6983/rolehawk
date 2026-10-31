import type {
  CommandInfo,
  InterviewState,
  LLMStatus,
  MemorySnapshot,
  Preferences,
  Profile,
  ProfileOverview,
  ProposalView,
  Question,
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
    name: "context",
    description: "Export the context pack.",
    read_only: true,
    background: false,
    release: "v1.0",
    params_schema: {},
  },
  {
    name: "memory",
    description: "Show memory files and pending proposals.",
    read_only: true,
    background: false,
    release: "v1.0",
    params_schema: {},
  },
  {
    name: "propose",
    description: "Propose a memory edit.",
    read_only: false,
    background: false,
    release: "v1.0",
    params_schema: {},
  },
  {
    name: "selftest",
    description: "Run a short background task.",
    read_only: true,
    background: true,
    release: "v1.0",
    params_schema: {},
  },
  {
    name: "spend",
    description: "Show AI spend this month and the cap.",
    read_only: true,
    background: false,
    release: "v1.0",
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
