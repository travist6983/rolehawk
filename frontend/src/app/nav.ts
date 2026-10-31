import {
  ChartColumnIcon,
  CompassIcon,
  RadioTowerIcon,
  SettingsIcon,
  SquareKanbanIcon,
  UserRoundIcon,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  description: string;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Pipeline", icon: SquareKanbanIcon, description: "Track every application" },
  { to: "/discover", label: "Discover", icon: CompassIcon, description: "Review ranked jobs" },
  { to: "/profile", label: "Profile", icon: UserRoundIcon, description: "Your source of truth" },
  { to: "/sources", label: "Sources", icon: RadioTowerIcon, description: "Where jobs come from" },
  { to: "/insights", label: "Insights", icon: ChartColumnIcon, description: "What's working" },
  { to: "/settings", label: "Settings", icon: SettingsIcon, description: "Claude, models, data" },
];

const FALLBACK: NavItem = { to: "/", label: "Offerbound", icon: SquareKanbanIcon, description: "" };

// Screens outside the sidebar that still need a name (e.g. for the chat context chip).
const OTHER_SCREENS: NavItem[] = [
  { to: "/onboarding", label: "Profile setup", icon: UserRoundIcon, description: "" },
  { to: "/applications", label: "Application", icon: SquareKanbanIcon, description: "" },
];

export function navItemFor(pathname: string): NavItem {
  const exact = NAV_ITEMS.find((item) => item.to === pathname);
  if (exact) return exact;
  const prefix = [...NAV_ITEMS, ...OTHER_SCREENS]
    .filter((item) => item.to !== "/")
    .find((item) => pathname.startsWith(item.to));
  return prefix ?? FALLBACK;
}
