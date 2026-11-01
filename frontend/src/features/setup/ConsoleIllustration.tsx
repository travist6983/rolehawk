import { cn } from "@/lib/utils";
import { PRODUCT_NAME } from "@/lib/brand";

export type ConsolePage = "signup" | "billing" | "keys";

/** What each drawing shows, for screen readers and as the visible caption. */
const DESCRIPTIONS: Record<ConsolePage, string> = {
  signup:
    "The sign-up page offers to continue with Google or with your email address. Either works.",
  billing:
    "On the Billing page, Buy credits sits next to your credit balance. Spend limits is further down the same page.",
  keys: `On the API keys page, Create key opens a short form: type ${PRODUCT_NAME} as the name, keep the Default workspace, then copy the key it shows you.`,
};

function Chrome({ path, children }: { path: string; children: React.ReactNode }) {
  return (
    <div aria-hidden className="overflow-hidden rounded-md border bg-card text-xs shadow-card">
      <div className="flex items-center gap-2 border-b bg-muted/60 px-2 py-1.5">
        <span className="flex gap-1">
          <span className="size-2 rounded-full bg-muted-foreground/30" />
          <span className="size-2 rounded-full bg-muted-foreground/30" />
          <span className="size-2 rounded-full bg-muted-foreground/30" />
        </span>
        <span className="truncate rounded bg-background px-2 py-0.5 text-muted-foreground">
          platform.claude.com{path}
        </span>
      </div>
      <div className="space-y-2 p-3">{children}</div>
    </div>
  );
}

function FakeButton({ children, highlight }: { children: React.ReactNode; highlight?: boolean }) {
  return (
    <span
      className={cn(
        "inline-block rounded border px-2 py-1",
        highlight
          ? "border-primary bg-primary/10 font-medium text-primary-text ring-2 ring-primary/40"
          : "text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

function Drawing({ page }: { page: ConsolePage }) {
  if (page === "signup") {
    return (
      <Chrome path="/">
        <p className="font-medium">Create your account</p>
        <div className="flex flex-col gap-1.5 sm:max-w-56">
          <FakeButton>Continue with Google</FakeButton>
          <FakeButton highlight>Continue with email</FakeButton>
        </div>
      </Chrome>
    );
  }
  if (page === "billing") {
    return (
      <Chrome path="/settings/billing">
        <p className="font-medium">Billing</p>
        <div className="flex flex-wrap items-center justify-between gap-2 rounded border p-2">
          <span>
            Credit balance <span className="font-medium">$0.00</span>
          </span>
          <FakeButton highlight>Buy credits</FakeButton>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 rounded border p-2">
          <span>Spend limits</span>
          <FakeButton>Set limit</FakeButton>
        </div>
      </Chrome>
    );
  }
  return (
    <Chrome path="/settings/keys">
      <div className="flex items-center justify-between gap-2">
        <p className="font-medium">API keys</p>
        <FakeButton highlight>Create key</FakeButton>
      </div>
      <div className="space-y-1.5 rounded border p-2">
        <p>
          Name: <span className="rounded border px-1">{PRODUCT_NAME}</span>
        </p>
        <p>
          Workspace: <span className="rounded border px-1">Default</span>
        </p>
        <div className="flex flex-wrap items-center justify-between gap-2 rounded bg-muted/60 p-1.5">
          <code>sk-ant-api03-••••••••••••</code>
          <FakeButton highlight>Copy</FakeButton>
        </div>
      </div>
    </Chrome>
  );
}

/**
 * A simplified drawing of a Claude Platform page, so people know what to look for. It is
 * drawn here, not a screenshot of Anthropic's site, and says so.
 */
export function ConsoleIllustration({ page }: { page: ConsolePage }) {
  return (
    <figure className="space-y-1.5">
      <Drawing page={page} />
      <figcaption className="text-xs text-muted-foreground">
        {DESCRIPTIONS[page]}{" "}
        <span className="italic">
          Illustration only; the real page may look a little different.
        </span>
      </figcaption>
    </figure>
  );
}
