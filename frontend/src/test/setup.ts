import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { setSessionToken } from "@/api/client";

import { FakeEventSource } from "./fakeEventSource";
import { server } from "./server";

// jsdom gaps that Radix UI and the app rely on. Types claim these exist; jsdom lacks them.
function polyfill(target: object, key: string, value: unknown): void {
  if (!(key in target) || (target as Record<string, unknown>)[key] === undefined) {
    Object.defineProperty(target, key, { value, configurable: true, writable: true });
  }
}

polyfill(window, "matchMedia", (query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
  dispatchEvent: () => false,
}));
polyfill(
  globalThis,
  "ResizeObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);
polyfill(Element.prototype, "scrollIntoView", () => undefined);
polyfill(Element.prototype, "hasPointerCapture", () => false);
polyfill(Element.prototype, "releasePointerCapture", () => undefined);

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  setSessionToken(null);
  FakeEventSource.reset();
  localStorage.clear();
  document.documentElement.className = "";
});

afterAll(() => {
  server.close();
});
