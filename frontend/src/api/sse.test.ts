import { describe, expect, it } from "vitest";

import { parseData, parseSSE, type SSEMessage } from "./sse";

function streamOf(...chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks)
        controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<SSEMessage[]> {
  const out: SSEMessage[] = [];
  for await (const message of parseSSE(stream)) out.push(message);
  return out;
}

describe("parseSSE", () => {
  it("parses named events with JSON data", async () => {
    const messages = await collect(
      streamOf('event: text\ndata: {"text":"Hi"}\n\n', "event: done\ndata: {}\n\n"),
    );
    expect(messages).toEqual([
      { event: "text", data: '{"text":"Hi"}' },
      { event: "done", data: "{}" },
    ]);
    const [first] = messages;
    expect(first && parseData(first)).toEqual({ text: "Hi" });
  });

  it("handles events split across chunk boundaries, including mid-CRLF", async () => {
    const messages = await collect(
      streamOf("event: te", "xt\r", "\ndata: one\r\n", "\r\nevent: done\r\ndata: x\r\n\r\n"),
    );
    expect(messages.map((m) => [m.event, m.data])).toEqual([
      ["text", "one"],
      ["done", "x"],
    ]);
  });

  it("joins multi-line data, ignores comments, and defaults the event name", async () => {
    const messages = await collect(
      streamOf(": keep-alive\n\ndata: line 1\ndata: line 2\nid: 42\n\n"),
    );
    expect(messages).toEqual([{ event: "message", data: "line 1\nline 2", id: "42" }]);
  });

  it("decodes multi-byte characters split between chunks", async () => {
    const bytes = new TextEncoder().encode("data: café ☕\n\n");
    const messages = await collect(streamOf(bytes.slice(0, 10), bytes.slice(10)));
    expect(messages[0]?.data).toBe("café ☕");
  });

  it("emits a final event even without a trailing blank line", async () => {
    expect(await collect(streamOf("event: done\ndata: last"))).toEqual([
      { event: "done", data: "last" },
    ]);
  });

  it("returns null for malformed JSON instead of throwing", () => {
    expect(parseData({ event: "x", data: "{nope" })).toBeNull();
  });
});
