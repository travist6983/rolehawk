import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

import { setSessionToken } from "@/api/client";

import { FakeEventSource } from "./fakeEventSource";
import { server } from "./server";

// Lazy routes compile on first use; Windows CI runners need longer than the 1s default.
configure({ asyncUtilTimeout: 5000 });

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

// React 18 only warns when a component that needs a ref isn't forwardRef; with Radix that
// silently breaks focus and exit animations (a closed overlay keeps swallowing clicks).
const REF_WARNING = "Function components cannot be given refs";
const refWarnings: string[] = [];
const consoleError = console.error.bind(console);

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
    const text = args.map(String).join(" ");
    if (text.includes(REF_WARNING)) refWarnings.push(text.slice(0, 300));
    consoleError(...args);
  });
});

afterEach(() => {
  const warnings = refWarnings.splice(0);
  if (warnings.length > 0) {
    throw new Error(`A component needs React.forwardRef:\n${warnings.join("\n")}`);
  }
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
