/** Semantic score bands from the design system: 80+ green, 60-79 amber, below 60 zinc. */
export function scoreTone(score: number): "high" | "mid" | "low" {
  if (score >= 80) return "high";
  if (score >= 60) return "mid";
  return "low";
}
