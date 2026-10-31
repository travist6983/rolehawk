const TASK_LABELS: Record<string, string> = {
  selftest: "Self-test",
  scrape: "Job search",
  rank: "Ranking",
  apply: "Application drafts",
};

export function taskLabel(kind: string): string {
  return TASK_LABELS[kind] ?? kind.replace(/[-_]/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
