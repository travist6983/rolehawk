import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { parseBlocks } from "@/lib/markdown";

import { MarkdownLite } from "./MarkdownLite";

describe("MarkdownLite", () => {
  it("parses headings, bullets, and paragraphs, skipping comments", () => {
    expect(
      parseBlocks("# Profile\n<!-- note -->\n## Skills\n- Python\n- React\nLoves\nshipping."),
    ).toEqual([
      { kind: "heading", level: 1, text: "Profile" },
      { kind: "heading", level: 2, text: "Skills" },
      { kind: "list", items: ["Python", "React"] },
      { kind: "paragraph", text: "Loves shipping." },
    ]);
  });

  it("drops the title and empty sections, and never renders HTML", () => {
    render(
      <MarkdownLite
        markdown={"# Profile\n## Summary\n## Skills\n- <img src=x onerror=alert(1)>\n"}
      />,
    );
    expect(screen.queryByText("Profile")).not.toBeInTheDocument();
    expect(screen.queryByText("Summary")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Skills" })).toBeInTheDocument();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("says so when a file has no content", () => {
    render(<MarkdownLite markdown={"# Facts\n<!-- learned in chat -->\n"} />);
    expect(screen.getByText("Nothing here yet.")).toBeInTheDocument();
  });
});
