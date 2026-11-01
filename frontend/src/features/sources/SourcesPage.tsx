import { PlusIcon, RadioTowerIcon } from "lucide-react";
import { useRef, useState } from "react";

import { usePortals } from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { CardGridSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";

import { AddPortalDialog } from "./AddPortalDialog";
import { PortalCard } from "./PortalCard";
import { SearchPanel } from "./SearchPanel";
import { Watchlist } from "./Watchlist";
import { PRODUCT_NAME } from "@/lib/brand";

export default function SourcesPage() {
  const portals = usePortals();
  const [filter, setFilter] = useState("all");
  const [adding, setAdding] = useState(false);
  const watchlist = useRef<HTMLElement>(null);

  if (portals.isPending) return <CardGridSkeleton />;
  if (portals.isError) {
    return (
      <EmptyState
        icon={RadioTowerIcon}
        title="Couldn't load your sources"
        description={`The ${PRODUCT_NAME} backend didn't answer. Check that it's still running.`}
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
  const feeds = portals.data.filter((p) => p.kind !== "ats" && !p.custom);
  // Sources that need a developer key stay out of the way unless the user has set one up.
  const openFeeds = feeds.filter((p) => p.secret_fields.length === 0);
  const keyedFeeds = feeds.filter((p) => p.secret_fields.length > 0);
  const keyedInUse = keyedFeeds.some((p) => p.ready || p.enabled);
  const custom = portals.data.filter((p) => p.custom);
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
        description={`Where ${PRODUCT_NAME} looks for jobs. Searches run on your computer and go straight to each job site.`}
      />
      <div className="space-y-8 px-5 pb-8 md:px-8">
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
              Searched by job title. Nothing to set up.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {openFeeds.map((portal) => (
              <PortalCard key={portal.id} portal={portal} />
            ))}
          </div>
          {keyedFeeds.length > 0 && (
            <details className="group rounded-lg border p-4" open={keyedInUse}>
              <summary className="cursor-pointer text-sm font-medium">
                Advanced: more sources that need a developer key
              </summary>
              <p className="mt-2 max-w-prose text-sm text-muted-foreground">
                Optional. These add more jobs (Adzuna covers the UK, Germany, Australia, India, and
                more; USAJOBS lists US federal jobs), but each asks you to register on its developer
                site for a free key. Keys are kept in your computer's keychain, and a source
                switches on when its key is saved.
              </p>
              <div className="mt-3 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {keyedFeeds.map((portal) => (
                  <PortalCard key={portal.id} portal={portal} />
                ))}
              </div>
            </details>
          )}
        </section>

        <section aria-labelledby="custom-heading" className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="custom-heading" className="text-lg font-semibold">
                Your sources
              </h2>
              <p className="text-sm text-muted-foreground">
                Careers pages and job boards you added. Each runs in a separate, sandboxed process.
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => {
                setAdding(true);
              }}
            >
              <PlusIcon /> Add a job site
            </Button>
          </div>
          {custom.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {custom.map((portal) => (
                <PortalCard key={portal.id} portal={portal} />
              ))}
            </div>
          ) : (
            <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
              None yet. Add a company's careers page or a niche job board.
            </p>
          )}
        </section>

        <section ref={watchlist} tabIndex={-1} aria-label="Watchlist" className="outline-none">
          <Watchlist filter={filter} onFilterChange={setFilter} />
        </section>
      </div>
      <AddPortalDialog open={adding} onOpenChange={setAdding} />
    </>
  );
}
