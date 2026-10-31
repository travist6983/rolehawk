import { PartyPopperIcon } from "lucide-react";

import { errorText } from "@/api/errors";
import { useAnswer, useInterview, useSkipQuestion } from "@/api/queries";
import { FormSkeleton } from "@/components/feedback/Skeletons";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

import { QuestionCard } from "./QuestionCard";

export function InterviewStep({ onDone }: { onDone: () => void }) {
  const interview = useInterview();
  const answer = useAnswer();
  const skip = useSkipQuestion();

  if (interview.isPending) return <FormSkeleton label="Loading questions" />;
  if (interview.isError) {
    return (
      <p role="alert">Couldn't load the questions: {errorText(interview.error, "unknown error")}</p>
    );
  }

  const { question, answered, remaining, complete } = interview.data;
  const total = answered + remaining;
  const percent = total === 0 ? 100 : Math.round((answered / total) * 100);
  const failure = answer.error ?? skip.error;

  if (complete || !question) {
    return (
      <div className="flex flex-col items-center gap-4 py-8 text-center">
        <PartyPopperIcon className="size-10 text-primary" aria-hidden />
        <h2 className="text-xl font-semibold">Your profile is ready</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          Everything you told me is in your profile and preferences. You can edit them any time on
          the Profile page.
        </p>
        <Button onClick={onDone}>Continue</Button>
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
        key={question.id}
        question={question}
        pending={answer.isPending || skip.isPending}
        error={failure ? errorText(failure, "Something went wrong. Try again.") : null}
        onAnswer={(value) => {
          skip.reset();
          answer.mutate({ questionId: question.id, value });
        }}
        onSkip={() => {
          answer.reset();
          skip.mutate(question.id);
        }}
      />
    </div>
  );
}
