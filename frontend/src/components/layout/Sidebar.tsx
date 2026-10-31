import { BriefcaseIcon } from "lucide-react";
import { NavLink } from "react-router";

import { NAV_ITEMS } from "@/app/nav";
import { useEventStream } from "@/features/events/EventStreamProvider";
import { cn } from "@/lib/utils";

import { ThemeToggle } from "./ThemeToggle";

const STATUS_TEXT = {
  open: "Connected",
  connecting: "Connecting…",
  reconnecting: "Reconnecting…",
} as const;

export function Brand() {
  return (
    <div className="flex items-center gap-2 font-semibold">
      <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
        <BriefcaseIcon className="size-4" aria-hidden />
      </span>
      Offerbound
    </div>
  );
}

export function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <ul className="space-y-0.5">
      {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
        <li key={to}>
          <NavLink
            to={to}
            end={to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150",
                isActive
                  ? "bg-primary/10 text-primary-text"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )
            }
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

export function ConnectionStatus() {
  const { status } = useEventStream();
  return (
    <span className="flex items-center gap-2 text-xs text-muted-foreground" role="status">
      <span
        aria-hidden
        className={cn(
          "size-2 rounded-full",
          status === "open" ? "bg-score-high" : "animate-pulse bg-score-mid",
        )}
      />
      {STATUS_TEXT[status]}
    </span>
  );
}

export function Sidebar() {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-y-0 left-0 hidden w-56 flex-col border-r bg-sidebar px-3 py-4 md:flex"
    >
      <div className="px-3 pb-6">
        <Brand />
      </div>
      <NavLinks />
      <div className="mt-auto flex items-center justify-between px-3">
        <ConnectionStatus />
        <ThemeToggle />
      </div>
    </nav>
  );
}
