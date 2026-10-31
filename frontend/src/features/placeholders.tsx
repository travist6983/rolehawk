import { SearchXIcon } from "lucide-react";
import { Link } from "react-router";

import { EmptyState } from "@/components/feedback/EmptyState";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <EmptyState icon={SearchXIcon} title="Page not found" description="That page doesn't exist.">
      <Button asChild>
        <Link to="/">Back to pipeline</Link>
      </Button>
    </EmptyState>
  );
}
