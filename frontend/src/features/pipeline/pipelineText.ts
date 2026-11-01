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
