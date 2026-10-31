import { Outlet } from "react-router";

import { MobileHeader } from "@/components/layout/MobileHeader";
import { Sidebar } from "@/components/layout/Sidebar";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatDrawer } from "@/features/chat/ChatDrawer";
import { ProgressTray } from "@/features/events/ProgressTray";

export function AppShell() {
  return (
    <TooltipProvider delayDuration={300}>
      <div className="min-h-dvh">
        <a
          href="#main"
          className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
        >
          Skip to content
        </a>
        <Sidebar />
        <div className="md:pl-56">
          <MobileHeader />
          <main id="main" tabIndex={-1} className="pb-24 outline-none">
            <Outlet />
          </main>
        </div>
        <ChatDrawer />
        <ProgressTray />
        <Toaster position="top-right" />
      </div>
    </TooltipProvider>
  );
}
