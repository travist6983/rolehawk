import { MenuIcon } from "lucide-react";
import { useState } from "react";

import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

import { Brand, NavLinks, SidebarFooter } from "./Sidebar";

/** Below 768px the espresso sidebar becomes a top bar with a menu sheet. */
export function MobileHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 bg-sidebar px-4 py-3 text-sidebar-foreground md:hidden">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <button
            type="button"
            aria-label="Open menu"
            className="grid size-9 cursor-pointer place-items-center rounded-full hover:bg-sidebar-active"
          >
            <MenuIcon className="size-5" aria-hidden />
          </button>
        </SheetTrigger>
        <SheetContent
          side="left"
          className="w-64 border-none bg-sidebar px-3.5 pt-6 pb-[18px] text-sidebar-foreground"
        >
          <SheetHeader className="p-0">
            <SheetTitle asChild>
              <div>
                <Brand className="px-2.5 pb-4 text-sidebar-foreground" />
              </div>
            </SheetTitle>
          </SheetHeader>
          <nav aria-label="Main">
            <NavLinks
              onNavigate={() => {
                setOpen(false);
              }}
            />
          </nav>
          <SidebarFooter />
        </SheetContent>
      </Sheet>
      <Brand className="text-[22px]" />
    </header>
  );
}
