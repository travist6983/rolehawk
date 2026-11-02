import { ArrowLeftIcon, PartyPopperIcon } from "lucide-react";

import { errorText } from "@/api/errors";
import { useAnswer, useInterview, useInterviewBack, useSkipQuestion } from "@/api/queries";
import { FormSkeleton } from "@/components/feedback/Skeletons";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

import { QuestionCard } from "./QuestionCard";

export function InterviewStep({ onDone }: { onDone: () => void }) {
  const interview = useInterview();
  const answer = useAnswer();
  const skip = useSkipQuestion();
  const back = useInterviewBack();

  if (interview.isPending) return <FormSkeleton label="Loading questions" />;
  if (interview.isError) {
    return (
      <p role="alert">Couldn't load the questions: {errorText(interview.error, "unknown error")}</p>
    );
  }

  const { question, answered, remaining, complete } = interview.data;
  const total = answered + remaining;
  const percent = total === 0 ? 100 : Math.round((answered / total) * 100);
  const failure = answer.error ?? skip.error ?? back.error;
  const resetAll = () => {
    answer.reset();
    skip.reset();
    back.reset();
  };

  if (complete || !question) {
    return (
      <div className="flex flex-col items-center gap-4 py-8 text-center">
        <PartyPopperIcon className="size-10 text-primary" aria-hidden />
        <h2 className="text-xl font-semibold">Your profile is ready</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          Everything you told me is in your profile and preferences. You can edit them any time on
          the Profile page.
        </p>
        <div className="flex items-center gap-2">
          {interview.data.can_go_back && (
            <Button
              variant="ghost"
              disabled={back.isPending}
              onClick={() => {
                back.mutate();
              }}
            >
              <ArrowLeftIcon aria-hidden />
              Back
            </Button>
          )}
          <Button onClick={onDone}>Continue</Button>
        </div>
        {back.error && (
          <p role="alert" className="text-sm text-destructive">
            {errorText(back.error, "Couldn't go back. Try again.")}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>
            {answered} answered · about {remaining} to go
          </span>
          <span className="font-mono">{percent}%</span>
        </div>
        <Progress value={percent} aria-label="Setup progress" className="h-1.5" />
      </div>
      <QuestionCard
        // A new card per question, and per saved answer when Back asks one again.
        key={`${question.id}|${question.skip_label}|${JSON.stringify(question.value)}`}
        question={question}
        pending={answer.isPending || skip.isPending || back.isPending}
        error={failure ? errorText(failure, "Something went wrong. Try again.") : null}
        canGoBack={interview.data.can_go_back}
        onAnswer={(value) => {
          resetAll();
          answer.mutate({ questionId: question.id, value });
        }}
        onSkip={() => {
          resetAll();
          skip.mutate(question.id);
        }}
        onBack={() => {
          resetAll();
          back.mutate();
        }}
      />
    </div>
  );
}
