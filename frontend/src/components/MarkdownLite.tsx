import { parseBlocks } from "@/lib/markdown";

/** Headings, bullets, and paragraphs from the memory files, rendered as React elements (never
 *  as HTML). Empty sections are dropped. The full editor arrives with the profile builder. */
export function MarkdownLite({ markdown }: { markdown: string }) {
  const blocks = parseBlocks(markdown).filter((block, index, all) => {
    if (block.kind !== "heading" || block.level === 1) return block.kind !== "heading";
    const next = all[index + 1];
    return next !== undefined && (next.kind !== "heading" || next.level > block.level);
  });
  if (blocks.length === 0)
    return <p className="text-sm text-muted-foreground">Nothing here yet.</p>;
  return (
    <div className="space-y-3 text-sm">
      {blocks.map((block, index) => {
        const key = `${block.kind}-${String(index)}`;
        if (block.kind === "heading") {
          return (
            <h3 key={key} className="pt-1 font-semibold first:pt-0">
              {block.text}
            </h3>
          );
        }
        if (block.kind === "list") {
          return (
            <ul key={key} className="list-disc space-y-1 pl-5">
              {block.items.map((item, i) => (
                <li key={`${key}-${String(i)}`}>{item}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={key} className="leading-relaxed">
            {block.text}
          </p>
        );
      })}
    </div>
  );
}
