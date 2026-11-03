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
  { value: "closed", label: "Past their deadline", filters: { status: "all", show: "closed" } },
] as const satisfies readonly { value: string; label: string; filters: JobFilters }[];

export type ShowValue = (typeof SHOW_OPTIONS)[number]["value"];

export function showValue(filters: JobFilters): ShowValue {
  if (filters.show === "saved") return "saved";
  if (filters.show === "dismissed") return "dismissed";
  if (filters.show === "closed") return "closed";
  if (filters.status === "ranked") return "ranked";
  if (filters.status === "unranked") return "unranked";
  return "all";
}

export const MIN_SCORES = [
  { value: "any", label: "Any score", score: null },
  { value: "60", label: "60 and up", score: 60 },
  { value: "70", label: "70 and up", score: 70 },
  { value: "80", label: "80 and up", score: 80 },
  { value: "85", label: "85 and up", score: 85 },
] as const;

/** The design's "Strong fits only" filter. */
export const STRONG_FIT = 85;

/** Discover opens on jobs that fit the user's preferences; the rest are a click away. */
export const DEFAULT_FILTERS: JobFilters = {
  status: "all",
  show: "active",
  sort: "score",
  fits_preferences: true,
};

/** True when anything narrows the list beyond the default view. */
export function isFiltered(filters: JobFilters): boolean {
  return Boolean(
    filters.q ||
    filters.min_score != null ||
    filters.portal_id ||
    filters.target ||
    filters.remote ||
    (filters.status && filters.status !== "all") ||
    (filters.show && filters.show !== "active"),
  );
}

const SKIP_REASONS: [keyof FilterCounts, string][] = [
  ["country", "in other countries"],
  ["location", "outside your locations"],
  ["salary", "below your salary floor"],
  ["excluded", "matched an excluded word"],
  ["already_ranked", "already ranked"],
  ["applied", "already in your pipeline"],
  ["dismissed", "dismissed"],
  ["closed", "past their deadline"],
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

export type OutsideReason = NonNullable<JobRow["outside_preferences"]>;

/** Why ranking new jobs skips a job, short enough for a table row. */
export const OUTSIDE_TEXT: Record<OutsideReason, string> = {
  country: "Other country",
  location: "Outside your locations",
  salary: "Below your salary floor",
  excluded: "Has an excluded word",
};

/** The longer version for the job sheet. */
export const OUTSIDE_DETAIL: Record<OutsideReason, string> = {
  country: "It's in a country outside your search.",
  location: "It isn't remote and isn't in one of your locations.",
  salary: "Its salary tops out below your floor.",
  excluded: "Its title or company has one of your excluded words or deal breakers.",
};

export const WORK_MODE: Record<NonNullable<JobRow["facts"]["work_mode"]>, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  "on-site": "On-site",
};

/** "Hybrid · 5+ yrs · React, TypeScript, Node.js +2": the posting's quick facts, or null. */
export function factsText(facts: JobRow["facts"], shown = 3): string | null {
  const skills = facts.skills.slice(0, shown).join(", ");
  const more = facts.skills.length - shown;
  const parts = [
    facts.work_mode && WORK_MODE[facts.work_mode],
    facts.years !== null && `${String(facts.years)}+ yrs`,
    skills && (more > 0 ? `${skills} +${String(more)}` : skills),
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : null;
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

/** The four parts behind a fit score, with their weights (backend fit/rubric.py WEIGHTS). */
export const FIT_PARTS = [
  { key: "experience", label: "Experience", weight: 35, hint: "Role, seniority, and domain" },
  { key: "skills", label: "Skills", weight: 30, hint: "The posting's must-haves" },
  { key: "career", label: "Career fit", weight: 20, hint: "Your goals and the work you enjoy" },
  { key: "logistics", label: "Logistics", weight: 15, hint: "Location, salary, schedule" },
] as const;

export type GateVerdict = "pass" | "check" | "fail";

/** How a gate verdict reads, per gate. */
export function gateText(gate: "eligibility" | "language", verdict: GateVerdict): string {
  if (gate === "eligibility") {
    return {
      pass: "You can hold this job",
      check: "Check you can hold this job",
      fail: "You may not be eligible",
    }[verdict];
  }
  return {
    pass: "Language requirements met",
    check: "Language bar may be above your level",
    fail: "Needs a language you don't list",
  }[verdict];
}

/** A short table note when a gate failed or needs checking ("Not eligible", "Check language"). */
export function gateNote(job: JobRow): { label: string; fail: boolean } | null {
  const gates = job.gates;
  if (!gates) return null;
  if (gates.eligibility.verdict === "fail") return { label: "Not eligible", fail: true };
  if (gates.language.verdict === "fail") return { label: "Language", fail: true };
  if (gates.deal_breaker) return { label: "Deal-breaker", fail: true };
  if (gates.eligibility.verdict === "check") return { label: "Check eligibility", fail: false };
  if (gates.language.verdict === "check") return { label: "Check language", fail: false };
  return null;
}

/** Whether gates are worth showing outside the job sheet (anything but a clean pass). */
export function needsAttention(gates: NonNullable<JobRow["gates"]>): boolean {
  return (
    gates.eligibility.verdict !== "pass" ||
    gates.language.verdict !== "pass" ||
    gates.deal_breaker !== ""
  );
}

/** "Closes in 3 days", "Closes today", "Closed Oct 30", or null when there's no deadline. */
export function deadlineText(job: Pick<JobRow, "closes_at" | "deadline">): string | null {
  if (!job.closes_at) return null;
  const [y, m, d] = job.closes_at.split("-").map(Number);
  const when = new Date(Date.UTC(y ?? 0, (m ?? 1) - 1, d ?? 1));
  const label = when.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
  if (job.deadline === "closed") return `Closed ${label}`;
  if (job.deadline !== "soon") return `Closes ${label}`;
  const now = new Date();
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const days = Math.round((when.getTime() - today) / 86_400_000);
  if (days <= 0) return "Closes today";
  return days === 1 ? "Closes tomorrow" : `Closes in ${String(days)} days`;
}

/** "Posted 2 months ago" for postings older than 30 days, or null. */
export function staleText(job: Pick<JobRow, "stale_days">): string | null {
  const days = job.stale_days;
  if (days === null) return null;
  if (days < 60) return `Posted ${String(days)} days ago`;
  return `Posted ${String(Math.round(days / 30))} months ago`;
}
