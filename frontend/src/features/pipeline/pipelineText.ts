/** Pure helpers for the Pipeline board. */

import type { Board, BoardCard, Stage } from "@/api/queries";

export const CLOSED_STAGES: Stage[] = ["rejected", "withdrawn", "ghosted"];

export const STAGE_NAMES: Record<Stage, string> = {
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

/** The stage a card gets when dropped on a column; null means "ask" (the Closed column). */
export function stageForColumn(board: Board, columnId: string): Stage | null {
  const column = board.columns.find((c) => c.id === columnId);
  if (!column || column.id === "closed") return null;
  return column.stages[0] ?? null;
}

export function columnIndexOf(board: Board, card: BoardCard): number {
  return board.columns.findIndex((c) => c.stages.includes(card.stage));
}

export function daysText(days: number): string {
  if (days === 0) return "today";
  return days === 1 ? "1 day" : `${String(days)} days`;
}

export const CHANNELS = [
  { value: "email", label: "Email" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "portal", label: "Application portal" },
] as const;

/** "This would be your first follow-up (at most two is the norm)." */
export function followUpText(card: Pick<BoardCard, "follow_ups">): string {
  const which = card.follow_ups === 0 ? "first" : "second and last";
  return `This would be your ${which} follow-up (at most two is the norm).`;
}

/** Cards whose next step is the user's (everything but waiting on the employer). */
export function waitsOnYou(card: Pick<BoardCard, "stage" | "next_action">): boolean {
  if (CLOSED_STAGES.includes(card.stage) || !card.next_action) return false;
  return card.next_action !== "Wait for a reply";
}

/** "3 cards are waiting on you." */
export function waitingText(count: number): string {
  if (count === 0) return "Nothing is waiting on you.";
  return count === 1 ? "1 card is waiting on you." : `${String(count)} cards are waiting on you.`;
}

/** The design groups the board into three phases. Columns not listed fall into the last. */
export const PHASES = [
  { name: "Your move", note: "Before you apply", columns: ["saved", "applying"] },
  {
    name: "In flight",
    note: "Waiting on them, mostly",
    columns: ["applied", "screen", "interview"],
  },
  { name: "Outcome", note: "", columns: ["offer", "closed"] },
] as const;

/** "Good morning" / "Good afternoon" / "Good evening". */
export function greeting(now: Date = new Date()): string {
  const hour = now.getHours();
  if (hour < 12) return "Good morning";
  return hour < 18 ? "Good afternoon" : "Good evening";
}
