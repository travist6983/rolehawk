import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { DocumentSettings } from "@/api/queries";
import { documentSettings } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

function documentsCard(): HTMLElement {
  const title = screen.getByText("Documents", { selector: "[data-slot=card-title]" });
  const card = title.closest<HTMLElement>("[data-slot=card]");
  if (!card) throw new Error("no Documents card");
  return card;
}

describe("Documents settings", () => {
  it("chooses templates and paper size", async () => {
    const patches: unknown[] = [];
    let current: DocumentSettings = documentSettings();
    server.use(
      http.get("/api/documents/settings", () => HttpResponse.json(current)),
      http.patch("/api/documents/settings", async ({ request }) => {
        const body = (await request.json()) as Partial<DocumentSettings> & { paper?: string };
        patches.push(body);
        current = {
          ...current,
          ...(body.cv_template ? { cv_template: body.cv_template } : {}),
          ...(body.paper === "a4" ? { paper: "a4", paper_auto: false } : {}),
        };
        return HttpResponse.json(current);
      }),
    );
    const { user } = await renderApp("/settings");
    await screen.findByRole("group", { name: "CV template" });
    const card = documentsCard();

    const cvGroup = within(card).getByRole("group", { name: "CV template" });
    expect(within(cvGroup).getByRole("radio", { name: /Classic/ })).toBeChecked();
    await user.click(within(cvGroup).getByRole("radio", { name: /Compact/ }));
    await waitFor(() => {
      expect(within(cvGroup).getByRole("radio", { name: /Compact/ })).toBeChecked();
    });
    expect(patches).toEqual([{ cv_template: "compact" }]);

    const letters = within(card).getByRole("group", { name: "Cover letter template" });
    expect(within(letters).getAllByRole("radio")).toHaveLength(2);

    expect(within(card).getByRole("combobox", { name: "Paper size" })).toHaveTextContent(
      "Automatic (Letter)",
    );
    await user.click(within(card).getByRole("combobox", { name: "Paper size" }));
    await user.click(screen.getByRole("option", { name: "A4" }));
    await waitFor(() => {
      expect(patches).toContainEqual({ paper: "a4" });
    });
  });

  it("previews a template with PDF and Word downloads", async () => {
    const { user } = await renderApp("/settings");
    await screen.findByRole("group", { name: "CV template" });
    await user.click(screen.getByRole("button", { name: "Preview Modern" }));

    const dialog = await screen.findByRole("dialog", { name: "Modern preview" });
    expect(within(dialog).getByTitle("Modern PDF preview")).toHaveAttribute(
      "src",
      "/api/templates/modern/preview",
    );
    expect(within(dialog).getByRole("link", { name: "Word (DOCX)" })).toHaveAttribute(
      "href",
      "/api/templates/modern/preview?format=docx",
    );
    expect(dialog).toHaveTextContent("Filled with your profile");
  });
});
