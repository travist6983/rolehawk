import type { EventSourceLike } from "@/features/events/EventStreamProvider";

/** In-memory EventSource: tests drive open/error/messages explicitly. */
export class FakeEventSource implements EventSourceLike {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;
  private listeners = new Map<string, ((event: MessageEvent<string>) => void)[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  static latest(): FakeEventSource {
    const instance = FakeEventSource.instances.at(-1);
    if (!instance) throw new Error("no EventSource created");
    return instance;
  }

  static reset(): void {
    FakeEventSource.instances = [];
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close(): void {
    this.closed = true;
  }

  open(): void {
    this.onopen?.(new Event("open"));
  }

  fail(): void {
    this.onerror?.(new Event("error"));
  }

  emit(type: string, data: unknown): void {
    const event = new MessageEvent<string>(type, {
      data: typeof data === "string" ? data : JSON.stringify(data),
    });
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

export const fakeFactory = (url: string) => new FakeEventSource(url);
