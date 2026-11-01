import { BriefcaseIcon, TerminalIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { onUnauthorized } from "@/api/client";
import { bootstrapSession, type SessionStatus } from "@/api/session";
import { PRODUCT_NAME } from "@/lib/brand";

function Unauthorized() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-4 p-6 text-center">
      <span className="grid size-12 place-items-center rounded-xl bg-primary text-primary-foreground">
        <BriefcaseIcon className="size-6" aria-hidden />
      </span>
      <h1 className="text-xl font-semibold">Open {PRODUCT_NAME} from its launcher</h1>
      <p className="text-sm text-muted-foreground">
        This page needs the private link {PRODUCT_NAME} opens when it starts. If you restarted the
        app, use the new link it opened, or start it again:
      </p>
      <code className="inline-flex items-center gap-2 rounded-md bg-muted px-3 py-2 font-mono text-sm">
        <TerminalIcon className="size-4" aria-hidden /> rolehawk
      </code>
    </main>
  );
}

/** Establishes the API session before rendering the app. */
export function SessionGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<SessionStatus | "loading">("loading");

  useEffect(() => {
    let active = true;
    bootstrapSession()
      .then((result) => {
        if (active) setStatus(result);
      })
      .catch(() => {
        if (active) setStatus("unauthorized");
      });
    const unsubscribe = onUnauthorized(() => {
      setStatus("unauthorized");
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  if (status === "loading") {
    return (
      <div
        role="status"
        className="grid min-h-dvh place-items-center text-sm text-muted-foreground"
      >
        Starting {PRODUCT_NAME}…
      </div>
    );
  }
  if (status === "unauthorized") return <Unauthorized />;
  return <>{children}</>;
}
