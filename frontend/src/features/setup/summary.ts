import type { ApplyResult } from "@/api/queries";

const NOUNS: Record<string, [string, string]> = {
  experience: ["role", "roles"],
  education: ["school", "schools"],
  skills: ["skill", "skills"],
  certifications: ["certification", "certifications"],
  projects: ["project", "projects"],
  achievements: ["achievement", "achievements"],
  languages: ["language", "languages"],
};

export function summarizeApply(result: Pick<ApplyResult, "added">): string {
  const parts = Object.entries(result.added).map(([key, n]) => {
    const [one, many] = NOUNS[key] ?? [key, key];
    return `${String(n)} ${n === 1 ? one : many}`;
  });
  return parts.length ? `Added ${parts.join(", ")}` : "Profile updated";
}
