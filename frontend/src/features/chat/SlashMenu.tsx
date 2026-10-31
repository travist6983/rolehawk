import type { CommandInfo } from "@/api/queries";
import { cn } from "@/lib/utils";

import { optionId } from "./slash";

interface SlashMenuProps {
  id: string;
  commands: CommandInfo[];
  activeIndex: number;
  onSelect: (command: CommandInfo) => void;
  onHover: (index: number) => void;
}

/** Listbox for the combobox in ChatInput. Keyboard handling lives in the input so focus never
 *  leaves the textarea (aria-activedescendant pattern). */
export function SlashMenu({ id, commands, activeIndex, onSelect, onHover }: SlashMenuProps) {
  if (commands.length === 0) {
    return (
      <div
        id={id}
        role="listbox"
        aria-label="Commands"
        className="px-3 py-2 text-sm text-muted-foreground"
      >
        No matching commands
      </div>
    );
  }
  return (
    <ul id={id} role="listbox" aria-label="Commands" className="max-h-64 overflow-y-auto py-1">
      {commands.map((command, index) => (
        <li
          key={command.name}
          id={optionId(id, index)}
          role="option"
          aria-selected={index === activeIndex}
          className={cn(
            "flex cursor-pointer flex-col gap-0.5 px-3 py-2 text-sm",
            index === activeIndex && "bg-accent text-accent-foreground",
          )}
          onMouseDown={(event) => {
            event.preventDefault(); // keep focus in the textarea
            onSelect(command);
          }}
          onMouseEnter={() => {
            onHover(index);
          }}
        >
          <span className="font-mono font-medium">/{command.name}</span>
          <span className="line-clamp-2 text-xs text-muted-foreground">{command.description}</span>
        </li>
      ))}
    </ul>
  );
}
