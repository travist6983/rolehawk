/** Minimal markdown helpers for the memory files (headings, bullets, paragraphs). */

export function stripComments(markdown: string): string {
  return markdown.replace(/<!--[\s\S]*?-->\n?/g, "");
}

export type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "paragraph"; text: string };

export function parseBlocks(markdown: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of stripComments(markdown).split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) continue;
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    const last = blocks.at(-1);
    if (heading?.[1] && heading[2] !== undefined) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
    } else if (bullet?.[1] !== undefined) {
      if (last?.kind === "list") last.items.push(bullet[1]);
      else blocks.push({ kind: "list", items: [bullet[1]] });
    } else if (last?.kind === "paragraph") {
      last.text += ` ${line.trim()}`;
    } else {
      blocks.push({ kind: "paragraph", text: line.trim() });
    }
  }
  return blocks;
}
