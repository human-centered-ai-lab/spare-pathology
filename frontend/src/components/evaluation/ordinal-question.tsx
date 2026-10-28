import { useCallback } from "react";
import { cn } from "@/lib/utils";
import type { SchemaQuestion } from "@/types";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface OrdinalQuestionProps {
  question: SchemaQuestion;
  title: string;
  description?: string;
  value: number | null;
  onSelect: (questionId: string, value: number) => void;
  readOnly: boolean;
  onMouseEnter?: () => void;
  isFocused?: boolean;
}

export function OrdinalQuestion({
  question,
  title,
  description,
  value,
  onSelect,
  readOnly,
  onMouseEnter,
  isFocused,
}: OrdinalQuestionProps) {
  const min = question.min ?? 1;
  const max = question.max ?? 5;
  const labels = question.labels ?? {};

  const handleSelect = useCallback(
    (score: number) => {
      if (readOnly) return;
      onSelect(question.id, score);
    },
    [question.id, onSelect, readOnly],
  );

  const scoreRange: number[] = [];
  for (let i = min; i <= max; i++) {
    scoreRange.push(i);
  }

  const buttons = (
    <div className="flex rounded-lg border border-border overflow-hidden">
      {scoreRange.map((score) => {
        const isFilled = value !== null && score <= value;
        const isSelected = value === score;
        const label = labels[String(score)] ?? "";

        return (
          <button
            key={score}
            type="button"
            disabled={readOnly}
            onClick={() => handleSelect(score)}
            className={cn(
              "flex-1 flex flex-col items-center gap-0.5 py-2 text-xs transition-all border-r border-border last:border-r-0",
              isFilled
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:bg-accent",
              isSelected && "bg-primary text-primary-foreground hover:bg-primary"
            )}
          >
            <span className="font-semibold text-[11px]">{score}</span>
            {label && (
              <span className="text-[10px] leading-tight">{label}</span>
            )}
          </button>
        );
      })}
    </div>
  );

  return (
    <div
      className={cn(
        "space-y-2.5 -mx-2 rounded-lg border border-transparent px-2.5 py-2 transition-all",
        isFocused && "border-primary/35 bg-primary/5 ring-1 ring-primary/20 shadow-sm",
      )}
      onMouseEnter={onMouseEnter}
    >
      <div>
        <p className="text-sm font-medium text-foreground">{title}</p>
        {description && (
          <p className="mt-1 text-xs text-muted-foreground">
            {description}
          </p>
        )}
      </div>

      {readOnly ? (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>{buttons}</TooltipTrigger>
            <TooltipContent>Ratings can not be changed when viewing as participant</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ) : buttons}
    </div>
  );
}
