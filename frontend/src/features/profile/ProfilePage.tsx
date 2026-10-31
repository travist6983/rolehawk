import { UserRoundIcon } from "lucide-react";

import { useMemory, useProposals } from "@/api/queries";
import { EmptyState } from "@/components/feedback/EmptyState";
import { MarkdownLite } from "@/components/MarkdownLite";
import { DocumentSkeleton } from "@/components/feedback/Skeletons";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useChat } from "@/features/chat/ChatProvider";
import { ProposalChip } from "@/features/memory/ProposalChip";

import { isBlankMemory } from "./memoryText";

function MemoryFile({ title, markdown }: { title: string; markdown: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <MarkdownLite markdown={markdown} />
      </CardContent>
    </Card>
  );
}

export default function ProfilePage() {
  const chat = useChat();
  const memory = useMemory();
  const proposals = useProposals();
  if (memory.isPending) return <DocumentSkeleton />;
  if (memory.isError)
    return (
      <div className="p-6" role="alert">
        Couldn't load your profile.
      </div>
    );

  const pending = proposals.data ?? [];
  const blank = isBlankMemory(memory.data.profile) && isBlankMemory(memory.data.facts);
  return (
    <>
      <PageHeader
        title="Profile"
        description="Your source of truth. Generated documents only use facts written here."
      />
      <div className="mx-auto max-w-3xl space-y-6 p-6">
        {pending.length > 0 && (
          <section aria-labelledby="pending-heading" className="space-y-2">
            <h2 id="pending-heading" className="text-sm font-semibold">
              Suggested updates ({pending.length})
            </h2>
            {pending.map((proposal) => (
              <ProposalChip key={proposal.id} proposal={proposal} />
            ))}
          </section>
        )}
        {blank ? (
          <EmptyState
            icon={UserRoundIcon}
            title="Your profile is empty"
            description="Upload a resume or answer a few questions and Offerbound builds your profile. Nothing is added without your OK."
            steps={[
              {
                title: "Connect Claude",
                description: "Add your API key so Offerbound can read your resume.",
                action: { label: "Open Settings", to: "/settings" },
              },
              {
                title: "Tell it about you",
                description: "Describe your experience and goals in the chat.",
                action: { label: "Open chat", onClick: chat.openDrawer },
              },
              {
                title: "Find jobs",
                description: "Accept the facts Claude suggests, then pick sources to search.",
                action: { label: "Choose sources", to: "/sources" },
              },
            ]}
          />
        ) : (
          <>
            <MemoryFile title="Profile" markdown={memory.data.profile} />
            <MemoryFile title="Preferences" markdown={memory.data.preferences} />
            <MemoryFile title="Facts" markdown={memory.data.facts} />
          </>
        )}
      </div>
    </>
  );
}
