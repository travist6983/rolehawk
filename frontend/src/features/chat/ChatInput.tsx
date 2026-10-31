import { ArrowUpIcon, SquareIcon } from "lucide-react";
import { forwardRef, useId, useMemo, useState } from "react";

import { useCommands, type CommandInfo } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import { filterCommands, optionId } from "./slash";
import { SlashMenu } from "./SlashMenu";

interface ChatInputProps {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

/** Message box with a slash-command menu. Type "/" to browse commands. */
export const ChatInput = forwardRef<HTMLTextAreaElement, ChatInputProps>(function ChatInput(
  { busy, onSend, onStop },
  ref,
) {
  const [value, setValue] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const listId = useId();
  const commands = useCommands();

  const slashQuery = /^\/[\w-]*$/.test(value) ? value.slice(1) : null;
  const matches = useMemo(
    () => (slashQuery === null ? [] : filterCommands(commands.data ?? [], slashQuery)),
    [commands.data, slashQuery],
  );
  const menuOpen = slashQuery !== null && !dismissed;
  const active = Math.min(activeIndex, Math.max(matches.length - 1, 0));

  const choose = (command: CommandInfo) => {
    setValue(`/${command.name} `);
    setActiveIndex(0);
  };

  const submit = () => {
    const text = value.trim();
    if (!text || busy) return;
    onSend(text);
    setValue("");
    setDismissed(false);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (menuOpen && matches.length > 0) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        setActiveIndex((active + step + matches.length) % matches.length);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        const command = matches[active];
        if (command) {
          event.preventDefault();
          choose(command);
          return;
        }
      }
    }
    if (menuOpen && event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation(); // close the menu, not the drawer
      setDismissed(true);
      return;
    }
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form
      className="relative border-t p-3"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      {menuOpen && (
        <div className="absolute right-3 bottom-full left-3 mb-2 overflow-hidden rounded-lg border bg-popover text-popover-foreground shadow-md">
          <SlashMenu
            id={listId}
            commands={matches}
            activeIndex={active}
            onSelect={choose}
            onHover={setActiveIndex}
          />
        </div>
      )}
      <div className="flex items-end gap-2">
        <Textarea
          ref={ref}
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
            setDismissed(false);
            setActiveIndex(0);
          }}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="Ask anything, or type / for commands"
          aria-label="Message"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={menuOpen}
          aria-controls={menuOpen ? listId : undefined}
          aria-activedescendant={
            menuOpen && matches.length > 0 ? optionId(listId, active) : undefined
          }
          className="max-h-40 min-h-10 resize-none"
        />
        {busy ? (
          <Button type="button" size="icon" variant="outline" aria-label="Stop" onClick={onStop}>
            <SquareIcon />
          </Button>
        ) : (
          <Button type="submit" size="icon" aria-label="Send" disabled={!value.trim()}>
            <ArrowUpIcon />
          </Button>
        )}
      </div>
    </form>
  );
});
