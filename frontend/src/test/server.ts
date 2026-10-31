import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import {
  commands,
  company,
  documentSettings,
  interviewState,
  jobPage,
  llmStatus,
  memory,
  portals,
  profileOverview,
  TEST_TOKEN,
} from "./fixtures";

/** Default API: a connected install with an empty pipeline. Tests override per case. */
export const handlers = [
  http.get("/api/session", () =>
    HttpResponse.json({ token: TEST_TOKEN, data_root: "/Users/ada/Offerbound", version: "0.1.0" }),
  ),
  http.post("/api/session", () => new HttpResponse(null, { status: 204 })),
  http.get("/api/tasks", () => HttpResponse.json([])),
  http.get("/api/commands", () => HttpResponse.json(commands)),
  http.get("/api/llm/status", () => HttpResponse.json(llmStatus())),
  http.get("/api/llm/models", () =>
    HttpResponse.json([
      {
        id: "claude-opus-5-5",
        display_name: "Claude Opus 5.5",
        max_input_tokens: null,
        max_output_tokens: null,
        extra: {},
      },
      {
        id: "claude-sonnet-5-5",
        display_name: "Claude Sonnet 5.5",
        max_input_tokens: null,
        max_output_tokens: null,
        extra: {},
      },
    ]),
  ),
  http.get("/api/memory", () => HttpResponse.json(memory())),
  http.get("/api/memory/proposals", () => HttpResponse.json([])),
  http.get("/api/profile", () => HttpResponse.json(profileOverview())),
  http.get("/api/setup/interview", () => HttpResponse.json(interviewState())),
  http.get("/api/setup/draft", () =>
    HttpResponse.json({ detail: "No setup draft" }, { status: 404 }),
  ),
  http.get("/api/setup/documents", () => HttpResponse.json([])),
  http.get("/api/portals", () => HttpResponse.json(portals())),
  http.get("/api/companies", () =>
    HttpResponse.json([
      company(),
      company({ id: 2, ats: "lever", slug: "palantir", name: "Palantir", industry: "Software" }),
    ]),
  ),
  http.get("/api/scrape/last", () => HttpResponse.json(null)),
  http.get("/api/jobs", () => HttpResponse.json(jobPage([]))),
  http.get("/api/documents/settings", () => HttpResponse.json(documentSettings())),
];

export const server = setupServer(...handlers);

/** A text/event-stream response, deliberately split mid-event to exercise the parser. */
export function sseResponse(events: [string, unknown][]): HttpResponse<ReadableStream> {
  const body = events
    .map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    .join("");
  const bytes = new TextEncoder().encode(body);
  const cut = Math.floor(bytes.length / 2);
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(bytes.slice(0, cut));
      controller.enqueue(bytes.slice(cut));
      controller.close();
    },
  });
  return new HttpResponse(stream, { headers: { "Content-Type": "text/event-stream" } });
}
