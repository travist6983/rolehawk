import { Skeleton } from "@/components/ui/skeleton";

/** Loading placeholders shaped like each screen, so content doesn't jump when it arrives. */

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="status" aria-label={label} aria-busy="true" className="space-y-6 p-6">
      {children}
      <span className="sr-only">{label}</span>
    </div>
  );
}

function Header() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-7 w-48" />
      <Skeleton className="h-4 w-72" />
    </div>
  );
}

export function BoardSkeleton() {
  return (
    <Labelled label="Loading pipeline">
      <Header />
      <div className="flex gap-4 overflow-hidden">
        {Array.from({ length: 5 }, (_, column) => (
          <div key={column} className="w-64 shrink-0 space-y-3">
            <Skeleton className="h-5 w-24" />
            {Array.from({ length: 3 - (column % 2) }, (_, card) => (
              <Skeleton key={card} className="h-24 w-full" />
            ))}
          </div>
        ))}
      </div>
    </Labelled>
  );
}

export function TableSkeleton({ label = "Loading jobs" }: { label?: string }) {
  return (
    <Labelled label={label}>
      <Header />
      <div className="space-y-2">
        <Skeleton className="h-9 w-full" />
        {Array.from({ length: 8 }, (_, row) => (
          <Skeleton key={row} className="h-12 w-full" />
        ))}
      </div>
    </Labelled>
  );
}

export function CardGridSkeleton({ label = "Loading sources" }: { label?: string }) {
  return (
    <Labelled label={label}>
      <Header />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, card) => (
          <Skeleton key={card} className="h-36 w-full" />
        ))}
      </div>
    </Labelled>
  );
}

export function ChartSkeleton() {
  return (
    <Labelled label="Loading insights">
      <Header />
      <div className="grid gap-4 md:grid-cols-2">
        {Array.from({ length: 4 }, (_, chart) => (
          <Skeleton key={chart} className="h-56 w-full" />
        ))}
      </div>
    </Labelled>
  );
}

export function FormSkeleton({ label = "Loading settings" }: { label?: string }) {
  return (
    <Labelled label={label}>
      <Header />
      {Array.from({ length: 3 }, (_, section) => (
        <div key={section} className="space-y-3 rounded-lg border p-4">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-9 w-full max-w-md" />
          <Skeleton className="h-9 w-full max-w-sm" />
        </div>
      ))}
    </Labelled>
  );
}

export function DocumentSkeleton() {
  return (
    <Labelled label="Loading profile">
      <Header />
      {Array.from({ length: 3 }, (_, block) => (
        <div key={block} className="space-y-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ))}
    </Labelled>
  );
}
