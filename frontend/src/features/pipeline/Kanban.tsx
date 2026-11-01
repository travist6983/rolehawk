import {
  DndContext,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { AlertTriangleIcon, ClockIcon, MailIcon, MoreHorizontalIcon } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";

import { errorText } from "@/api/errors";
import {
  useMoveApplication,
  type Board,
  type BoardCard,
  type BoardColumn,
  type Stage,
} from "@/api/queries";
import { ScoreBadge } from "@/components/ScoreBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

import { FollowUpDialog } from "./FollowUpDialog";
import {
  CLOSED_STAGES,
  columnIndexOf,
  daysText,
  STAGE_NAMES,
  stageForColumn,
} from "./pipelineText";

interface Picked {
  id: number;
  from: number;
  target: number;
}

function CardMenu({ card, onMove }: { card: BoardCard; onMove: (stage: Stage) => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          size="icon"
          variant="ghost"
          className="size-7"
          aria-label={`Move ${card.title} at ${card.company}`}
          onPointerDown={(event) => {
            event.stopPropagation(); // the menu, not a drag
          }}
        >
          <MoreHorizontalIcon />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Move to</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {(Object.keys(STAGE_NAMES) as Stage[])
          .filter((stage) => stage !== card.stage)
          .map((stage) => (
            <DropdownMenuItem
              key={stage}
              onSelect={() => {
                onMove(stage);
              }}
            >
              {STAGE_NAMES[stage]}
            </DropdownMenuItem>
          ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function KanbanCard({
  card,
  picked,
  instructionsId,
  dragging,
  onKeyDown,
  onMove,
  onFollowUp,
}: {
  card: BoardCard;
  picked: boolean;
  instructionsId: string;
  dragging: React.RefObject<boolean>;
  onKeyDown: (event: React.KeyboardEvent<HTMLElement>, card: BoardCard) => void;
  onMove: (stage: Stage) => void;
  onFollowUp?: (card: BoardCard) => void;
}) {
  const { setNodeRef, listeners, transform, isDragging } = useDraggable({
    id: `card-${String(card.application_id)}`,
    data: { card },
  });
  const style = transform
    ? { transform: `translate3d(${String(transform.x)}px, ${String(transform.y)}px, 0)` }
    : undefined;
  const closed = CLOSED_STAGES.includes(card.stage);
  return (
    <article
      ref={setNodeRef}
      style={style}
      {...listeners}
      tabIndex={0}
      aria-roledescription="movable card"
      aria-describedby={instructionsId}
      aria-label={`${card.title} at ${card.company}, ${STAGE_NAMES[card.stage]}`}
      onKeyDown={(event) => {
        onKeyDown(event, card);
      }}
      className={cn(
        "cursor-grab touch-none space-y-1.5 rounded-lg border bg-card p-3 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 active:cursor-grabbing",
        isDragging && "relative z-20 shadow-lg",
        picked && "ring-[3px] ring-primary",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-xs text-muted-foreground">{card.company}</p>
          <Link
            to={`/applications/${String(card.application_id)}`}
            className="line-clamp-2 font-medium hover:underline"
            tabIndex={-1}
            onClick={(event) => {
              if (dragging.current) event.preventDefault();
            }}
          >
            {card.title}
          </Link>
        </div>
        {card.score !== null && <ScoreBadge score={card.score} />}
      </div>
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <ClockIcon className="size-3.5" aria-hidden />
          {closed ? STAGE_NAMES[card.stage] : `${daysText(card.days_in_stage)} in stage`}
        </span>
        <CardMenu card={card} onMove={onMove} />
      </div>
      {card.next_action && (
        <p
          className={cn(
            "flex items-start gap-1 text-xs",
            card.flags > 0 ? "text-destructive" : "text-foreground",
          )}
        >
          {card.flags > 0 && <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />}
          {card.next_action}
        </p>
      )}
      {card.follow_up_due && onFollowUp && (
        <Button
          size="sm"
          variant="outline"
          className="h-7 w-full text-xs"
          // A button inside a draggable card: don't start a drag or a keyboard move.
          onPointerDown={(event) => {
            event.stopPropagation();
          }}
          onKeyDown={(event) => {
            event.stopPropagation();
          }}
          onClick={() => {
            onFollowUp(card);
          }}
        >
          <MailIcon /> Draft a follow-up
        </Button>
      )}
    </article>
  );
}

function KanbanColumn({
  column,
  highlighted,
  children,
}: {
  column: BoardColumn;
  highlighted: boolean;
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });
  const headingId = useId();
  return (
    <section
      ref={setNodeRef}
      aria-labelledby={headingId}
      className={cn(
        "flex w-64 shrink-0 flex-col gap-2 rounded-xl bg-muted/50 p-2 transition-colors motion-reduce:transition-none",
        (isOver || highlighted) && "bg-primary/10 ring-2 ring-primary/40",
      )}
    >
      <h2
        id={headingId}
        className="flex items-center justify-between px-1 pt-1 text-sm font-medium"
      >
        {column.label}
        <span className="rounded-full bg-background px-2 text-xs text-muted-foreground tabular-nums">
          {column.cards.length}
        </span>
      </h2>
      <div className="flex min-h-24 flex-col gap-2">{children}</div>
    </section>
  );
}

export function Kanban({ board }: { board: Board }) {
  const move = useMoveApplication();
  const navigate = useNavigate();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const [picked, setPicked] = useState<Picked | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [closing, setClosing] = useState<BoardCard | null>(null);
  const [followingUp, setFollowingUp] = useState<BoardCard | null>(null);
  const dragging = useRef(false);
  const instructionsId = useId();

  const doMove = (card: BoardCard, stage: Stage) => {
    if (stage === card.stage) return;
    setAnnouncement(`Moved ${card.title} to ${STAGE_NAMES[stage]}.`);
    move.mutate(
      { id: card.application_id, stage },
      { onError: (error) => toast.error(errorText(error, "Couldn't move the application")) },
    );
  };

  const dropOn = (card: BoardCard, columnId: string) => {
    const column = board.columns.find((c) => c.id === columnId);
    if (!column || column.stages.includes(card.stage)) return;
    const stage = stageForColumn(board, columnId);
    if (stage) doMove(card, stage);
    else setClosing(card); // Closed: ask which kind
  };

  const onDragEnd = (event: DragEndEvent) => {
    const card = (event.active.data.current as { card?: BoardCard } | undefined)?.card;
    if (card && event.over) dropOn(card, String(event.over.id));
    window.setTimeout(() => {
      dragging.current = false;
    }, 0);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLElement>, card: BoardCard) => {
    if (event.target !== event.currentTarget) return; // keys inside the menu button
    const label = (i: number) => board.columns[i]?.label ?? "";
    if (!picked || picked.id !== card.application_id) {
      if (event.key === " ") {
        event.preventDefault();
        const from = columnIndexOf(board, card);
        setPicked({ id: card.application_id, from, target: from });
        setAnnouncement(
          `Picked up ${card.title}. Use the left and right arrow keys to choose a column, Space to drop, Escape to cancel.`,
        );
      } else if (event.key === "Enter") {
        void navigate(`/applications/${String(card.application_id)}`);
      }
      return;
    }
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const delta = event.key === "ArrowRight" ? 1 : -1;
      const target = Math.min(Math.max(picked.target + delta, 0), board.columns.length - 1);
      setPicked({ ...picked, target });
      setAnnouncement(`Over ${label(target)}.`);
    } else if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      const target = board.columns[picked.target];
      setPicked(null);
      if (!target || picked.target === picked.from) {
        setAnnouncement(`${card.title} stayed in ${label(picked.from)}.`);
      } else {
        dropOn(card, target.id);
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      setPicked(null);
      setAnnouncement(`Cancelled. ${card.title} stayed in ${label(picked.from)}.`);
    }
  };

  return (
    <>
      <p id={instructionsId} className="sr-only">
        Press Space to pick up a card, the left and right arrow keys to choose a column, and Space
        again to drop it. Press Enter to open the application.
      </p>
      <p aria-live="assertive" className="sr-only">
        {announcement}
      </p>
      <DndContext
        sensors={sensors}
        onDragStart={() => {
          dragging.current = true;
        }}
        onDragEnd={onDragEnd}
        onDragCancel={() => {
          dragging.current = false;
        }}
        accessibility={{
          screenReaderInstructions: { draggable: "Press Space to pick up this card." },
        }}
      >
        <div className="flex gap-3 overflow-x-auto pb-4" role="list" aria-label="Pipeline">
          {board.columns.map((column, index) => (
            <div key={column.id} role="listitem">
              <KanbanColumn column={column} highlighted={picked?.target === index}>
                {column.cards.map((card) => (
                  <KanbanCard
                    key={card.application_id}
                    card={card}
                    picked={picked?.id === card.application_id}
                    instructionsId={instructionsId}
                    dragging={dragging}
                    onKeyDown={onKeyDown}
                    onMove={(stage) => {
                      doMove(card, stage);
                    }}
                    onFollowUp={setFollowingUp}
                  />
                ))}
              </KanbanColumn>
            </div>
          ))}
        </div>
      </DndContext>
      {followingUp && (
        <FollowUpDialog
          card={followingUp}
          onClose={() => {
            setFollowingUp(null);
          }}
        />
      )}
      <Dialog
        open={closing !== null}
        onOpenChange={(open) => {
          if (!open) setClosing(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Close this application</DialogTitle>
            <DialogDescription>
              {closing ? `${closing.title} at ${closing.company}. ` : ""}What happened?
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap gap-2">
            {CLOSED_STAGES.map((stage) => (
              <Button
                key={stage}
                variant={stage === "rejected" ? "default" : "outline"}
                onClick={() => {
                  if (closing) doMove(closing, stage);
                  setClosing(null);
                }}
              >
                {STAGE_NAMES[stage]}
              </Button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
