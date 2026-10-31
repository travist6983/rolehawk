import { RadioTowerIcon } from "lucide-react";
import { useRef, useState } from "react";

import { usePortals } from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { CardGridSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";

import { PortalCard } from "./PortalCard";
import { SearchPanel } from "./SearchPanel";
import { Watchlist } from "./Watchlist";

export default function SourcesPage() {
  const portals = usePortals();
  const [filter, setFilter] = useState("all");
  const watchlist = useRef<HTMLElement>(null);

  if (portals.isPending) return <CardGridSkeleton />;
  if (portals.isError) {
    return (
      <EmptyState
        icon={RadioTowerIcon}
        title="Couldn't load your sources"
        description="The Offerbound backend didn't answer. Check that it's still running."
      >
        <Button
          className="mt-6"
          onClick={() => {
            void portals.refetch();
          }}
        >
          Try again
        </Button>
      </EmptyState>
    );
  }

  const boards = portals.data.filter((p) => p.kind === "ats");
  const feeds = portals.data.filter((p) => p.kind !== "ats");
  const manageCompanies = (ats: string) => {
    setFilter(ats);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    watchlist.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    watchlist.current?.focus({ preventScroll: true });
  };

  return (
    <>
      <PageHeader
        title="Sources"
        description="Where Offerbound looks for jobs. Searches run on your computer and go straight to each job site."
      />
      <div className="space-y-8 p-6">
        <SearchPanel portals={portals.data} />

        <section aria-labelledby="boards-heading" className="space-y-3">
          <div>
            <h2 id="boards-heading" className="text-lg font-semibold">
              Company job boards
            </h2>
            <p className="text-sm text-muted-foreground">
              Public boards from the hiring systems companies use. Searched per company in your
              watchlist.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {boards.map((portal) => (
              <PortalCard key={portal.id} portal={portal} onManageCompanies={manageCompanies} />
            ))}
          </div>
        </section>

        <section aria-labelledby="feeds-heading" className="space-y-3">
          <div>
            <h2 id="feeds-heading" className="text-lg font-semibold">
              Job feeds
            </h2>
            <p className="text-sm text-muted-foreground">
              Searched by job title. Adzuna and USAJOBS need a free API key, kept in your keychain.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {feeds.map((portal) => (
              <PortalCard key={portal.id} portal={portal} />
            ))}
          </div>
        </section>

        <section ref={watchlist} tabIndex={-1} aria-label="Watchlist" className="outline-none">
          <Watchlist filter={filter} onFilterChange={setFilter} />
        </section>
      </div>
    </>
  );
}
