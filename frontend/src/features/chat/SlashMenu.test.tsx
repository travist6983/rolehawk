import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { commands } from "@/test/fixtures";
import { testQueryClient } from "@/test/render";

import { ChatInput } from "./ChatInput";
import { filterCommands, parseSlashCommand } from "./slash";

describe("filterCommands", () => {
  it("puts name-prefix matches before other matches", () => {
    expect(filterCommands(commands, "s").map((c) => c.name)).toEqual([
      "selftest",
      "spend",
      "memory",
      "propose",
    ]);
    expect(filterCommands(commands, "sp").map((c) => c.name)).toEqual(["spend"]);
    expect(filterCommands(commands, "background").map((c) => c.name)).toEqual(["selftest"]);
    expect(filterCommands(commands, "")).toHaveLength(commands.length);
  });
});

describe("parseSlashCommand", () => {
  it("parses names and optional JSON params", () => {
    expect(parseSlashCommand("/spend")).toEqual({ name: "spend", params: {} });
    expect(parseSlashCommand('/selftest {"steps": 2}')).toEqual({
      name: "selftest",
      params: { steps: 2 },
    });
    expect(parseSlashCommand("/selftest {broken")).toEqual({ name: "selftest", params: {} });
    expect(parseSlashCommand("hello")).toBeNull();
  });
});

function renderInput(onSend = vi.fn()) {
  render(
    <QueryClientProvider client={testQueryClient()}>
      <ChatInput busy={false} onSend={onSend} onStop={vi.fn()} />
    </QueryClientProvider>,
  );
  return { onSend, input: screen.getByRole("combobox", { name: "Message" }) };
}

describe("slash menu in ChatInput", () => {
  it("opens on '/', filters as you type, and links options for screen readers", async () => {
    const user = userEvent.setup();
    const { input } = renderInput();
    expect(input).toHaveAttribute("aria-expanded", "false");

    await user.type(input, "/");
    const listbox = await screen.findByRole("listbox", { name: "Commands" });
    expect(input).toHaveAttribute("aria-expanded", "true");
    expect(input).toHaveAttribute("aria-controls", listbox.id);
    expect(await screen.findAllByRole("option")).toHaveLength(commands.length);

    await user.type(input, "mem");
    const options = screen.getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([
      expect.stringContaining("/memory"),
      expect.stringContaining("/propose"), // description mentions memory
    ]);
    expect(input).toHaveAttribute("aria-activedescendant", options[0]?.id);
  });

  it("navigates with arrow keys and selects with Enter without sending", async () => {
    const user = userEvent.setup();
    const { input, onSend } = renderInput();
    await user.type(input, "/");
    await screen.findAllByRole("option");
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(screen.getAllByRole("option")[2]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowUp}");
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{Enter}");
    expect(input).toHaveValue("/memory ");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onSend).not.toHaveBeenCalled();

    await user.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith("/memory");
    expect(input).toHaveValue("");
  });

  it("closes with Escape and wraps around with ArrowUp", async () => {
    const user = userEvent.setup();
    const { input } = renderInput();
    await user.type(input, "/");
    await screen.findAllByRole("option");
    await user.keyboard("{ArrowUp}");
    expect(screen.getAllByRole("option").at(-1)).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("selects an option with the mouse", async () => {
    const user = userEvent.setup();
    const { input } = renderInput();
    await user.type(input, "/sp");
    await user.click(await screen.findByRole("option", { name: /\/spend/ }));
    expect(input).toHaveValue("/spend ");
  });

  it("sends with Enter, keeps newlines with Shift+Enter, and ignores blank input", async () => {
    const user = userEvent.setup();
    const { input, onSend } = renderInput();
    await user.type(input, "   {Enter}");
    expect(onSend).not.toHaveBeenCalled();
    await user.clear(input);
    await user.type(input, "line one{Shift>}{Enter}{/Shift}line two{Enter}");
    expect(onSend).toHaveBeenCalledWith("line one\nline two");
  });
});
