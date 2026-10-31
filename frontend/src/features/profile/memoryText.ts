import { stripComments } from "@/lib/markdown";

/** True when a memory file has nothing but headings and comments. */
export function isBlankMemory(markdown: string): boolean {
  return stripComments(markdown)
    .split("\n")
    .every((line) => line.trim() === "" || line.trim().startsWith("#"));
}
