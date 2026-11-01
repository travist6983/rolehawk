import {
  DndContext,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { MailIcon, MoreHorizontalIcon } from "lucide-react";
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
import { FitRuler } from "@/components/ScoreBadge";
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
  PHASES,
  STAGE_NAMES,
  stageForColumn,
  waitsOnYou,
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
          className="-my-1 size-6 text-muted-foreground"
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
  const urgent = waitsOnYou(card);
  const title = (
    <Link
      to={`/applications/${String(card.application_id)}`}
      className={cn(
        "hover:underline",
        closed
          ? "text-sm font-medium text-foreground-2"
          : "font-serif text-[16.5px] leading-tight font-medium text-pretty",
      )}
      tabIndex={-1}
      onClick={(event) => {
        if (dragging.current) event.preventDefault();
      }}
    >
      {closed ? card.company : card.title}
    </Link>
  );
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
        "cursor-grab touch-none outline-offset-2 focus-visible:outline-2 focus-visible:outline-primary active:cursor-grabbing",
        closed
          ? "flex items-start justify-between gap-2 border-b border-dashed px-1 py-2"
          : "flex flex-col gap-[7px] rounded-lg bg-card px-3 pt-3 pb-[11px] shadow-card transition-shadow hover:shadow-card-hover",
        isDragging && "relative z-20 shadow-lg",
        picked && "outline-2 outline-primary",
      )}
    >
      {closed ? (
        <>
          <div className="flex min-w-0 flex-col gap-px">
            {title}
            <span className="text-[13px] text-muted-foreground">
              {STAGE_NAMES[card.stage]} · {card.title}
            </span>
          </div>
          <CardMenu card={card} onMove={onMove} />
        </>
      ) : (
        <>
          <div className="flex items-start justify-between gap-1">
            <span className="min-w-0 text-[12.5px] leading-tight font-semibold tracking-[0.04em] break-words text-foreground-2 uppercase">
              {card.company}
            </span>
            <span className="flex flex-none items-center gap-1 text-[13px] text-muted-foreground">
              <span aria-hidden>{card.days_in_stage}d</span>
              <span className="sr-only">{daysText(card.days_in_stage)} in stage</span>
              <CardMenu card={card} onMove={onMove} />
            </span>
          </div>
          {title}
          {card.score !== null && <FitRuler score={card.score} />}
          {card.next_action && (
            <p
              className={cn(
                "text-[13.5px] leading-snug",
                urgent ? "font-semibold text-primary-text" : "text-muted-foreground",
              )}
            >
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
        </>
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
        "flex min-w-0 flex-1 flex-col gap-2.5 rounded-lg pb-6 transition-colors motion-reduce:transition-none",
        column.id === "closed" && "gap-1.5",
        (isOver || highlighted) && "bg-accent outline-2 outline-primary/40",
      )}
    >
      <h3 id={headingId} className="flex items-baseline gap-1.5 p-0.5 text-sm font-semibold">
        {column.label}
        <span className="font-medium text-muted-foreground tabular-nums">
          {column.cards.length}
        </span>
      </h3>
      <div className="flex min-h-24 flex-col gap-2.5">{children}</div>
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
      if (event.altKey && (event.key === "ArrowRight" || event.key === "ArrowLeft")) {
        // The design's shortcut: move one column without picking the card up.
        event.preventDefault();
        const from = columnIndexOf(board, card);
        const target = board.columns[from + (event.key === "ArrowRight" ? 1 : -1)];
        if (target) dropOn(card, target.id);
        return;
      }
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
        again to drop it. Alt with an arrow key moves it one column. Press Enter to open the
        application.
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
        <div className="overflow-x-auto pb-4">
          <div
            className="grid min-w-max grid-cols-[minmax(348px,2fr)_minmax(528px,3fr)_minmax(348px,2fr)] gap-7"
            role="list"
            aria-label="Pipeline"
          >
            {PHASES.map((phase, p) => {
              const ids: readonly string[] = phase.columns;
              const columns = board.columns.filter(
                (c) =>
                  ids.includes(c.id) ||
                  (p === PHASES.length - 1 &&
                    !PHASES.some((x) => (x.columns as readonly string[]).includes(c.id))),
              );
              return (
                <div key={phase.name} className="flex min-w-0 flex-col gap-3">
                  <h2 className="flex items-baseline gap-2.5 border-b border-foreground pb-2">
                    <span className="font-serif text-xl font-medium italic">{phase.name}</span>
                    {phase.note && (
                      <span className="text-[13.5px] text-muted-foreground">{phase.note}</span>
                    )}
                  </h2>
                  <div className="flex flex-1 gap-3">
                    {columns.map((column) => {
                      const index = board.columns.indexOf(column);
                      return (
                        <div key={column.id} role="listitem" className="flex min-w-0 flex-1">
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
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
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
