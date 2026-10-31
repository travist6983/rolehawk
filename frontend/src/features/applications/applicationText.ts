/** Pure helpers for /apply and the application screen. */

import type { Flag, Stage } from "@/api/queries";

export const STAGE_LABELS: Record<Stage, string> = {
  saved: "Saved",
  applying: "Applying",
  applied: "Applied",
  screen: "Screen",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  ghosted: "Ghosted",
};

/** How each kind of review flag is labeled; serious ones are shown in the destructive color. */
export const FLAG_KINDS: Record<Flag["kind"], { label: string; serious: boolean }> = {
  unsupported: { label: "Not in your profile", serious: true },
  stretch: { label: "Stretch", serious: false },
  unaddressed: { label: "Requirement skipped", serious: false },
  style: { label: "Cliché", serious: false },
  ats: { label: "ATS", serious: true },
};

/** Flags for one document whose location is `prefix` or inside it ("experience.0" covers
 * "experience.0.bullets.2"). */
export function flagsAt(flags: Flag[], document: Flag["document"], prefix: string): Flag[] {
  return flags.filter(
    (f) =>
      f.document === document && (f.location === prefix || f.location.startsWith(`${prefix}.`)),
  );
}

/** One bullet per line in the editor. */
export function linesToList(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.replace(/^\s*[-•*]\s*/, "").trim())
    .filter(Boolean);
}

/** Paragraphs separated by blank lines in the editor. */
export function textToParagraphs(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((p) => p.replace(/\s*\n\s*/g, " ").trim())
    .filter(Boolean);
}

export function listToCommaText(items: string[]): string {
  return items.join(", ");
}

export function commaTextToList(text: string): string[] {
  return text
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** The /apply task's result, read defensively (task results are untyped JSON). */
export interface ApplyOutcome {
  status: "ready" | "needs_review" | "below_threshold";
  application_id: number | null;
  fit: { score: number; threshold: number; reasons: string[]; must_have_gaps: string[] };
}

export function readOutcome(result: unknown): ApplyOutcome | null {
  if (!result || typeof result !== "object") return null;
  const r = result as Partial<ApplyOutcome>;
  if (r.status !== "ready" && r.status !== "needs_review" && r.status !== "below_threshold")
    return null;
  if (!r.fit || typeof r.fit.score !== "number") return null;
  return {
    status: r.status,
    application_id: typeof r.application_id === "number" ? r.application_id : null,
    fit: r.fit,
  };
}
