/**
 * Server-Sent Events parser for fetch() streams. EventSource only supports GET, so streamed
 * POST responses (chat replies) are parsed here, following the WHATWG event-stream format.
 */

export interface SSEMessage {
  event: string;
  data: string;
  id?: string;
}

class EventAssembler {
  private event = "";
  private data: string[] = [];
  private id: string | undefined;

  /** Feed one line; returns a message when a blank line completes one. */
  line(line: string): SSEMessage | null {
    if (line === "") return this.dispatch();
    if (line.startsWith(":")) return null; // comment / keep-alive
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.event = value;
    else if (field === "data") this.data.push(value);
    else if (field === "id" && !value.includes("\0")) this.id = value;
    return null;
  }

  dispatch(): SSEMessage | null {
    if (this.data.length === 0) {
      this.event = "";
      return null;
    }
    const message: SSEMessage = { event: this.event || "message", data: this.data.join("\n") };
    if (this.id !== undefined) message.id = this.id;
    this.event = "";
    this.data = [];
    return message;
  }
}

export async function* parseSSE(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<SSEMessage, void, undefined> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  const assembler = new EventAssembler();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }); // multi-byte chars may split chunks
      // A trailing \r may be the first half of \r\n split across chunks: hold it back.
      const heldCR = buffer.endsWith("\r");
      const lines = (heldCR ? buffer.slice(0, -1) : buffer).split(/\r\n|\n|\r/);
      buffer = (lines.pop() ?? "") + (heldCR ? "\r" : "");
      for (const line of lines) {
        const message = assembler.line(line);
        if (message) yield message;
      }
    }
    buffer += decoder.decode();
    if (buffer !== "") {
      for (const line of buffer.split(/\r\n|\n|\r/).filter((l) => l !== "")) assembler.line(line);
    }
    const last = assembler.dispatch(); // a stream may end without a trailing blank line
    if (last) yield last;
  } finally {
    reader.releaseLock();
  }
}

/** Parse `data` as JSON, returning null for malformed payloads instead of throwing. */
export function parseData(message: SSEMessage): unknown {
  try {
    return JSON.parse(message.data) as unknown;
  } catch {
    return null;
  }
}
