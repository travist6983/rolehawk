/** Pure helpers for Discover: the "show" menu, filter summaries, and job display text. */

import type { FilterCounts, JobFilters, JobRow } from "@/api/queries";
import { plural } from "@/lib/format";

/** One menu covers both the ranking status and the saved/dismissed views. */
export const SHOW_OPTIONS = [
  { value: "all", label: "All jobs", filters: { status: "all", show: "active" } },
  { value: "ranked", label: "Ranked", filters: { status: "ranked", show: "active" } },
  { value: "unranked", label: "Not ranked yet", filters: { status: "unranked", show: "active" } },
  { value: "saved", label: "Saved", filters: { status: "all", show: "saved" } },
  { value: "dismissed", label: "Dismissed", filters: { status: "all", show: "dismissed" } },
] as const satisfies readonly { value: string; label: string; filters: JobFilters }[];

export type ShowValue = (typeof SHOW_OPTIONS)[number]["value"];

export function showValue(filters: JobFilters): ShowValue {
  if (filters.show === "saved") return "saved";
  if (filters.show === "dismissed") return "dismissed";
  if (filters.status === "ranked") return "ranked";
  if (filters.status === "unranked") return "unranked";
  return "all";
}

export const MIN_SCORES = [
  { value: "any", label: "Any score", score: null },
  { value: "60", label: "60 and up", score: 60 },
  { value: "70", label: "70 and up", score: 70 },
  { value: "80", label: "80 and up", score: 80 },
] as const;

export const DEFAULT_FILTERS: JobFilters = { status: "all", show: "active", sort: "score" };

/** True when anything narrows the list beyond the default view. */
export function isFiltered(filters: JobFilters): boolean {
  return Boolean(
    filters.q ||
    filters.min_score != null ||
    filters.portal_id ||
    filters.remote ||
    (filters.status && filters.status !== "all") ||
    (filters.show && filters.show !== "active"),
  );
}

const SKIP_REASONS: [keyof FilterCounts, string][] = [
  ["location", "outside your locations"],
  ["salary", "below your salary floor"],
  ["excluded", "matched an excluded word"],
  ["already_ranked", "already ranked"],
  ["applied", "already in your pipeline"],
  ["dismissed", "dismissed"],
];

/** "Skipped 12: 8 outside your locations, 4 below your salary floor." or null. */
export function skippedSummary(counts: FilterCounts): string | null {
  const parts = SKIP_REASONS.filter(([key]) => counts[key] > 0).map(
    ([key, text]) => `${counts[key].toLocaleString("en")} ${text}`,
  );
  if (parts.length === 0) return null;
  const total = SKIP_REASONS.reduce((sum, [key]) => sum + counts[key], 0);
  return `Skipped ${total.toLocaleString("en")}: ${parts.join(", ")}.`;
}

export function whereText(job: Pick<JobRow, "location" | "remote">): string {
  if (job.location && job.remote && !/remote/i.test(job.location)) {
    return `${job.location} (remote)`;
  }
  return job.location ?? (job.remote ? "Remote" : "Location not stated");
}

export function selectionText(count: number): string {
  return `${plural(count, "job")} selected`;
}

/** Job links come from third parties: only http(s) URLs become links. */
export function safeUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}
