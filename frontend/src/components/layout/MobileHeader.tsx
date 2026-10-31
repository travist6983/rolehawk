import { MenuIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

import { Brand, ConnectionStatus, NavLinks } from "./Sidebar";
import { ThemeToggle } from "./ThemeToggle";

export function MobileHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-30 flex items-center gap-2 border-b bg-background/95 px-4 py-2 backdrop-blur md:hidden">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Open menu">
            <MenuIcon />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-64 p-3">
          <SheetHeader className="px-3">
            <SheetTitle asChild>
              <div>
                <Brand />
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
          <div className="mt-auto px-3">
            <ConnectionStatus />
          </div>
        </SheetContent>
      </Sheet>
      <Brand />
      <div className="ml-auto">
        <ThemeToggle />
      </div>
    </header>
  );
}
