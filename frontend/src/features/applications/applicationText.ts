/** Pure helpers for /apply and the application screen. */

import type {
  CoverLetter,
  CvDocument,
  Flag,
  RegenerateSection,
  RequirementView,
  Stage,
} from "@/api/queries";

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

export const CHANNEL_LABELS: Record<"email" | "linkedin" | "portal", string> = {
  email: "email",
  linkedin: "LinkedIn",
  portal: "application portal",
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

/** The part of the documents a "Rewrite" redoes for a flagged line. */
export function sectionFor(flag: Flag): RegenerateSection | null {
  if (flag.document === "cover_letter") return "cover_letter";
  if (flag.location === "headline" || flag.location === "summary") return "summary";
  if (/^(experience|projects)\./.test(flag.location)) return "experience";
  if (flag.location === "skills" || flag.location.startsWith("skills.")) return "skills";
  return null;
}

/** Only single bullets and paragraphs can be dropped in one click. */
export function canDrop(flag: Flag): boolean {
  return /^experience\.\d+\.bullets\.\d+$|^paragraphs\.\d+$/.test(flag.location);
}

/** The documents without the flagged bullet or paragraph (unchanged if it already moved). */
export function dropLine(
  cv: CvDocument,
  letter: CoverLetter,
  flag: Flag,
): { cv: CvDocument; letter: CoverLetter } {
  const bullet = /^experience\.(\d+)\.bullets\.(\d+)$/.exec(flag.location);
  if (flag.document === "cv" && bullet) {
    const [role, line] = [Number(bullet[1]), Number(bullet[2])];
    const experience = cv.experience.map((r, i) =>
      i === role && r.bullets[line] === flag.text
        ? { ...r, bullets: r.bullets.filter((_, j) => j !== line) }
        : r,
    );
    return { cv: { ...cv, experience }, letter };
  }
  const paragraph = /^paragraphs\.(\d+)$/.exec(flag.location);
  if (flag.document === "cover_letter" && paragraph) {
    const at = Number(paragraph[1]);
    if (letter.paragraphs[at] !== flag.text) return { cv, letter };
    return { cv, letter: { ...letter, paragraphs: letter.paragraphs.filter((_, i) => i !== at) } };
  }
  return { cv, letter };
}

/** The instruction "Soften" pre-fills for a stretch. */
export function softenInstruction(flag: Flag): string {
  const line = flag.text.length > 300 ? `${flag.text.slice(0, 297)}…` : flag.text;
  return `Soften this line so I can defend it in an interview: "${line}" (${flag.issue})`.slice(
    0,
    1000,
  );
}

/** Keyword coverage from the ATS check, in plain words. */
export const KEYWORD_STATUS: Record<
  NonNullable<RequirementView["keyword"]>,
  { label: string; tone: string }
> = {
  covered: { label: "Matched", tone: "text-score-high" },
  synonym: { label: "Only under another name", tone: "text-caution" },
  missing_have: { label: "In your profile, not in this CV", tone: "text-destructive" },
  gap: { label: "Not in your profile", tone: "text-muted-foreground" },
};
