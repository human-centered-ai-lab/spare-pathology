import { useMemo, useCallback, useEffect, useRef } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { OrdinalQuestion } from "@/components/evaluation/ordinal-question";
import { TextQuestion } from "@/components/evaluation/text-question";
import { FailureReason } from "@/components/evaluation/failure-reason";
import { renderQuestionTemplate } from "@/lib/question-placeholders";
import { cn } from "@/lib/utils";
import type { RatingSchema, FailureReasonConfig } from "@/types";

interface RatingFormProps {
  imageLabel?: string;
  questionAttributes?: Record<string, string | number | boolean>;
  valueScopeKey?: string | number;
  currentStatus?: "not_opened" | "opened" | "partial" | "complete";
  schema: RatingSchema;
  responses: Record<string, number | string | string[] | null>;
  uncertainty: boolean;
  uncertaintyEnabled: boolean;
  readOnly: boolean;
  onSaveResponse: (questionId: string, value: number) => void;
  onSaveTextResponse: (questionId: string, value: string) => void;
  onSaveUncertainty: (value: boolean) => void;
  onSaveFailureReason: (value: string | string[] | null) => void;
  onFocusQuestion?: (index: number) => void;
  focusedQuestionIndex?: number;
}

export function RatingForm({
  schema,
  valueScopeKey,
  currentStatus,
  responses,
  uncertainty,
  uncertaintyEnabled,
  readOnly,
  onSaveResponse,
  onSaveTextResponse,
  onSaveUncertainty,
  onSaveFailureReason,
  onFocusQuestion,
  focusedQuestionIndex,
  imageLabel,
  questionAttributes,
}: RatingFormProps) {
  const questions = schema.questions ?? [];
  const failureConfig = schema.failure_reason;
  const answeredCount = questions.filter((question) => {
    const value = responses[question.id];
    if (value === null || value === undefined) return false;
    if (typeof value === "string") return value.trim().length > 0;
    return true;
  }).length;
  const derivedStatus =
    questions.length === 0
      ? "not_opened"
      : answeredCount === 0
        ? "not_opened"
        : answeredCount === questions.length
          ? "complete"
          : "partial";
  const status = currentStatus ?? derivedStatus;

  // Check whether the failure reason conditional trigger is met
  const showFailureReason = useMemo(() => {
    if (!failureConfig || !failureConfig.enabled) return false;
    if (!failureConfig.condition) return true;

    const { type, operator, value: threshold } = failureConfig.condition;

    const compare = (numValue: number): boolean => {
      switch (operator) {
        case "<=": case "less_than_or_equal": return numValue <= threshold;
        case "<": case "less_than": return numValue < threshold;
        case ">=": case "greater_than_or_equal": return numValue >= threshold;
        case ">": case "greater_than": return numValue > threshold;
        case "==": case "===": case "equals": return numValue === threshold;
        case "!=": case "!==": return numValue !== threshold;
        default: return false;
      }
    };

    if (type === "any_ordinal") {
      const ordinalIds = (schema.questions ?? [])
        .filter((q) => q.type === "ordinal")
        .map((q) => q.id);
      return ordinalIds.some((qid) => {
        const val = responses[qid];
        if (val === null || val === undefined) return false;
        const num = typeof val === "number" ? val : parseFloat(String(val));
        return !isNaN(num) && compare(num);
      });
    }

    // Conditions without a type also refer to a specific question.
    const questionId = failureConfig.condition.question_id;
    if (!questionId) return false;
    const responseValue = responses[questionId];
    if (responseValue === null || responseValue === undefined) return false;
    const numValue = typeof responseValue === "number" ? responseValue : parseFloat(String(responseValue));
    return !isNaN(numValue) && compare(numValue);
  }, [failureConfig, responses, schema.questions]);

  const failureReasonValue = useMemo(() => {
    const val = responses["failure_reason"];
    if (val === null || val === undefined) return null;
    if (Array.isArray(val)) return val as string[];
    return String(val);
  }, [responses]);

  // Auto-clear failure reason when condition becomes false
  const prevShowRef = useRef(showFailureReason);
  useEffect(() => {
    if (prevShowRef.current && !showFailureReason && failureReasonValue !== null) {
      onSaveFailureReason(null);
    }
    prevShowRef.current = showFailureReason;
  }, [showFailureReason, failureReasonValue, onSaveFailureReason]);

  const handleUncertaintyChange = useCallback(
    (checked: boolean | "indeterminate") => {
      if (typeof checked === "boolean") {
        onSaveUncertainty(checked);
      }
    },
    [onSaveUncertainty],
  );

  if (questions.length === 0) {
    return (
      <ScrollArea className="w-[24rem] shrink-0 border-l border-border bg-card">
        <div className="flex h-full items-center justify-center p-5">
          <p className="text-sm text-muted-foreground">
            No rating schema configured for this study.
          </p>
        </div>
      </ScrollArea>
    );
  }

  return (
    <ScrollArea className="w-[24rem] shrink-0 border-l border-border bg-card">
      <div className="p-5 space-y-5">
        <div className="flex items-baseline justify-between gap-3">
          <div className="flex items-baseline gap-2">
            <h2 className="text-sm font-semibold">Rating</h2>
            {imageLabel && (
              <p className="text-xs text-muted-foreground">{imageLabel}</p>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>{answeredCount}/{questions.length} questions answered</span>
            <span
              className={cn(
                "h-2 w-2 rounded-full shrink-0",
                status === "complete"
                  ? "bg-success"
                  : status === "partial"
                    ? "bg-warning"
                    : "bg-muted-foreground/30",
              )}
            />
          </div>
        </div>

        <Separator />

        <div className="space-y-2">
          {questions.map((q, idx) => {
            let element: React.ReactNode = null;

            if (q.type === "ordinal") {
              const currentValue = responses[q.id];
              const numValue =
                typeof currentValue === "number"
                  ? currentValue
                  : null;

              element = (
                <OrdinalQuestion
                  question={q}
                  title={renderQuestionTemplate(q.name, questionAttributes)}
                  description={renderQuestionTemplate(q.description, questionAttributes) || undefined}
                  value={numValue}
                  onSelect={onSaveResponse}
                  readOnly={readOnly}
                  onMouseEnter={() => onFocusQuestion?.(idx)}
                  isFocused={focusedQuestionIndex === idx}
                />
              );
            }

            if (q.type === "free_text") {
              const currentValue = responses[q.id];
              const strValue =
                currentValue != null ? String(currentValue) : "";

              element = (
                <TextQuestion
                  question={q}
                  title={renderQuestionTemplate(q.name, questionAttributes)}
                  description={renderQuestionTemplate(q.description, questionAttributes) || undefined}
                  value={strValue}
                  onSave={onSaveTextResponse}
                  readOnly={readOnly}
                  onMouseEnter={() => onFocusQuestion?.(idx)}
                  isFocused={focusedQuestionIndex === idx}
                />
              );
            }

            if (!element) return null;

            const questionKey =
              q.type === "free_text"
                ? `${q.id}:${String(valueScopeKey ?? "")}`
                : q.id;

            return (
              <div key={questionKey}>
                {element}
              </div>
            );
          })}
        </div>

        {/* Failure reason section */}
        {showFailureReason && failureConfig && (
          <>
            <Separator />
            <FailureReason
              config={failureConfig as FailureReasonConfig}
              value={failureReasonValue}
              onSave={onSaveFailureReason}
              readOnly={readOnly}
            />
          </>
        )}

        {/* Uncertainty checkbox */}
        {uncertaintyEnabled && (
          <>
            <Separator />
            <div className="flex items-center gap-2.5 rounded-lg border border-border bg-accent/50 px-3 py-2.5">
              <Checkbox
                checked={uncertainty}
                onCheckedChange={handleUncertaintyChange}
                disabled={readOnly}
              />
              <label className="text-xs text-foreground cursor-pointer leading-tight">
                I am uncertain about this rating
              </label>
            </div>
          </>
        )}
      </div>
    </ScrollArea>
  );
}
