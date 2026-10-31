import { Button } from "@/components/ui/button";

export function PipelinePage() {
  return (
    <section className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Pipeline</h1>
      <p className="text-muted-foreground mt-2">
        No applications yet. The kanban board arrives in Chunk 10.
      </p>
      <Button className="mt-6">Get started</Button>
    </section>
  );
}
