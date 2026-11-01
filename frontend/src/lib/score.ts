/** Semantic score bands: 80+ high, 60-79 mid, below 60 low. */
export function scoreTone(score: number): "high" | "mid" | "low" {
  if (score >= 80) return "high";
  if (score >= 60) return "mid";
  return "low";
}

/** The fit in a word, as the design labels it. */
export function fitWord(score: number): string {
  if (score >= 90) return "Strong fit";
  if (score >= 80) return "Good fit";
  return "Fair fit";
}

/** Where a score sits on the fit ruler, which runs from 50 (left) to 100 (right). */
export function rulerPercent(score: number): number {
  return Math.max(0, Math.min(100, (score - 50) * 2));
}
