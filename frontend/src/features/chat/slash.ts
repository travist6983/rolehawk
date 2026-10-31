import type { CommandInfo } from "@/api/queries";

/** Commands matching what follows the slash: name prefix matches first, then other matches. */
export function filterCommands(commands: CommandInfo[], query: string): CommandInfo[] {
  const q = query.trim().toLowerCase();
  if (!q) return commands;
  const prefix = commands.filter((c) => c.name.startsWith(q));
  const other = commands.filter(
    (c) => !c.name.startsWith(q) && (c.name.includes(q) || c.description.toLowerCase().includes(q)),
  );
  return [...prefix, ...other];
}

export function optionId(listId: string, index: number): string {
  return `${listId}-option-${String(index)}`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/** Parse "/name {json}" into a command call. Text after the name that isn't JSON is ignored. */
export function parseSlashCommand(
  text: string,
): { name: string; params: Record<string, unknown> } | null {
  const match = /^\/([\w-]+)\s*(.*)$/s.exec(text.trim());
  if (!match?.[1]) return null;
  const rest = (match[2] ?? "").trim();
  let params: Record<string, unknown> = {};
  if (rest.startsWith("{")) {
    try {
      params = asRecord(JSON.parse(rest));
    } catch {
      params = {};
    }
  }
  return { name: match[1], params };
}
