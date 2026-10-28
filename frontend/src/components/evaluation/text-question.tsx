import { useCallback } from "react";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { SchemaQuestion } from "@/types";

interface TextQuestionProps {
  question: SchemaQuestion;
  title: string;
  description?: string;
  value: string;
  onSave: (questionId: string, value: string) => void;
  readOnly: boolean;
  onMouseEnter?: () => void;
  isFocused?: boolean;
}

export function TextQuestion({
  question,
  title,
  description,
  value,
  onSave,
  readOnly,
  onMouseEnter,
  isFocused,
}: TextQuestionProps) {
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newValue = e.target.value;
      onSave(question.id, newValue);
    },
    [onSave, question.id],
  );

  return (
    <div
      className={cn(
        "space-y-2 -mx-2 rounded-lg border border-transparent px-2.5 py-2 transition-all",
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

      <Textarea
        value={value}
        onChange={handleChange}
        disabled={readOnly}
        placeholder="Note any artifacts or observations…"
        className="min-h-[72px] resize-y text-sm"
      />
    </div>
  );
}
