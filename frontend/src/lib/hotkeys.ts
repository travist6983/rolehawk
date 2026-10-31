import { useEffect, useLayoutEffect, useRef } from "react";

export function isMac(): boolean {
  const platform =
    (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform ??
    navigator.platform;
  return /mac|iphone|ipad/i.test(platform);
}

export function modKeyLabel(): string {
  return isMac() ? "⌘" : "Ctrl ";
}

/** Global shortcut. With `mod`, either Cmd or Ctrl counts, so it works on every OS. */
export function useHotkey(key: string, options: { mod?: boolean }, handler: () => void): void {
  const latest = useRef(handler);
  useLayoutEffect(() => {
    latest.current = handler;
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== key.toLowerCase()) return;
      if (options.mod && !(event.metaKey || event.ctrlKey)) return;
      event.preventDefault();
      latest.current();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [key, options.mod]);
}
