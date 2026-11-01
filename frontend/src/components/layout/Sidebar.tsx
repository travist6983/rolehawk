import { NavLink } from "react-router";

import { useJobs, usePipeline } from "@/api/queries";
import { NAV_ITEMS } from "@/app/nav";
import { useChat } from "@/features/chat/ChatProvider";
import { DEFAULT_FILTERS } from "@/features/discover/discoverText";
import { useEventStream } from "@/features/events/EventStreamProvider";
import { PRODUCT_NAME } from "@/lib/brand";
import { modKeyLabel } from "@/lib/hotkeys";
import { cn } from "@/lib/utils";

import { ThemeToggle } from "./ThemeToggle";

const STATUS_TEXT = {
  open: "Connected",
  connecting: "Connecting…",
  reconnecting: "Reconnecting…",
} as const;

export function Brand({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "font-serif text-[25px] leading-none font-medium tracking-[-0.01em]",
        className,
      )}
    >
      {PRODUCT_NAME}
    </div>
  );
}

/** Counts beside Pipeline and Discover, as in the design ("8", "8 new"). */
function useNavBadges(): Partial<Record<string, string>> {
  const board = usePipeline();
  const jobs = useJobs(DEFAULT_FILTERS);
  const total = board.data?.total;
  const fresh = jobs.data?.pages[0]?.stats.unranked;
  return {
    "/": total ? String(total) : undefined,
    "/discover": fresh ? `${String(fresh)} new` : undefined,
  };
}

export function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const badges = useNavBadges();
  return (
    <ul className="space-y-0.5">
      {NAV_ITEMS.map(({ to, label }) => {
        const badge = badges[to];
        return (
          <li key={to}>
            <NavLink
              to={to}
              end={to === "/"}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "flex items-baseline justify-between gap-2 rounded-md px-2.5 py-[9px] text-[15px] font-medium transition-colors duration-150 hover:bg-sidebar-active",
                  isActive ? "bg-sidebar-active text-sidebar-foreground" : "text-sidebar-muted",
                )
              }
            >
              {label}
              {badge && (
                <span
                  className={cn(
                    "text-[13.5px] font-semibold tabular-nums",
                    to === "/discover" ? "text-sidebar-badge" : "text-sidebar-muted",
                  )}
                >
                  {badge}
                </span>
              )}
            </NavLink>
          </li>
        );
      })}
    </ul>
  );
}

export function ConnectionStatus() {
  const { status } = useEventStream();
  return (
    <span className="flex items-center gap-[7px] text-[13px] font-medium" role="status">
      <span
        aria-hidden
        className={cn(
          "size-[7px] rounded-full",
          status === "open" ? "bg-sidebar-live" : "animate-pulse bg-sidebar-badge",
        )}
      />
      {STATUS_TEXT[status]}
    </span>
  );
}

/** "Ranking new jobs" with a hairline progress bar while /rank runs. */
function RankingProgress() {
  const { tasks } = useEventStream();
  const running = tasks.find(
    (t) => t.kind === "rank" && (t.status === "queued" || t.status === "running"),
  );
  if (!running) return null;
  const percent = Math.round((running.progress ?? 0) * 100);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between text-[13px] font-medium text-sidebar-muted">
        <span>Ranking new jobs</span>
        <span className="tabular-nums">{percent}%</span>
      </div>
      <div className="h-0.5 bg-sidebar-active" aria-hidden>
        <div
          className="h-0.5 bg-sidebar-foreground transition-[width] duration-500"
          style={{ width: `${String(percent)}%` }}
        />
      </div>
    </div>
  );
}

function AskClaude() {
  const chat = useChat();
  return (
    <button
      type="button"
      onClick={chat.openDrawer}
      aria-keyshortcuts="Meta+K Control+K"
      className="flex cursor-pointer items-center justify-between rounded-full bg-sidebar-foreground px-3.5 py-[9px] text-sm font-semibold text-sidebar focus-visible:outline-sidebar-foreground"
    >
      <span>Ask Claude</span>
      <kbd className="font-mono text-xs font-medium">{modKeyLabel()}K</kbd>
    </button>
  );
}

/** The bottom of the sidebar: ranking progress, Ask Claude, connection and theme. */
export function SidebarFooter() {
  return (
    <div className="mt-auto flex flex-col gap-3.5 px-2.5">
      <RankingProgress />
      <AskClaude />
      <div className="flex items-center justify-between text-sidebar-muted">
        <ConnectionStatus />
        <ThemeToggle />
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-y-0 left-0 hidden w-[220px] flex-col gap-0.5 overflow-y-auto bg-sidebar px-3.5 pt-6 pb-[18px] text-sidebar-foreground md:flex"
    >
      <Brand className="px-2.5 pb-6" />
      <NavLinks />
      <SidebarFooter />
    </nav>
  );
}
