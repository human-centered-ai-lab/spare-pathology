import { useState } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  GripVertical,
  ChevronRight,
  Trash2,
  ArrowUp,
  ArrowDown,
} from "lucide-react";
import type { SchemaQuestion } from "@/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface QuestionCardProps {
  question: SchemaQuestion;
  index: number;
  total: number;
  disabled?: boolean;
  leaving?: boolean;
  defaultExpanded?: boolean;
  onChange: (updated: SchemaQuestion) => void;
  onDelete: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

export function QuestionCard({
  question,
  index,
  total,
  disabled,
  leaving,
  defaultExpanded = false,
  onChange,
  onDelete,
  onMoveUp,
  onMoveDown,
}: QuestionCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: question.id, disabled });

  const style = {
    transform: CSS.Translate.toString(transform),
    transition: isDragging ? "none" : transition,
    zIndex: isDragging ? 10 : undefined,
    opacity: isDragging ? 0.5 : undefined,
  };

  function updateField<K extends keyof SchemaQuestion>(
    key: K,
    value: SchemaQuestion[K],
  ) {
    onChange({ ...question, [key]: value });
  }

  function handleMinMaxChange(field: "min" | "max", raw: string) {
    const num = parseInt(raw, 10);
    if (isNaN(num)) return;
    const updated = { ...question, [field]: num };

    const min = field === "min" ? num : (question.min ?? 0);
    const max = field === "max" ? num : (question.max ?? 5);
    if (min < max) {
      const newLabels: Record<string, string> = {};
      for (let i = min; i <= max; i++) {
        newLabels[String(i)] = question.labels?.[String(i)] ?? "";
      }
      updated.labels = newLabels;
    }
    onChange(updated);
  }

  function handleLabelChange(score: string, label: string) {
    onChange({
      ...question,
      labels: { ...question.labels, [score]: label },
    });
  }

  const scoreRange: number[] = [];
  if (question.type === "ordinal") {
    const min = question.min ?? 0;
    const max = question.max ?? 5;
    for (let i = min; i <= max; i++) {
      scoreRange.push(i);
    }
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "rounded-md border border-border bg-muted",
        "animate-in fade-in duration-150",
        leaving && "!opacity-0 transition-opacity duration-150",
      )}
      {...attributes}
    >
      {/* Collapsed header row */}
      <div className="flex items-center gap-1.5 px-3 py-2">
        <div
          className={cn(
            "flex items-center gap-1.5 shrink-0",
            !disabled && "cursor-grab active:cursor-grabbing",
          )}
          {...listeners}
        >
          <GripVertical
            className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
          />
          <Badge
            variant={question.type === "ordinal" ? "default" : "secondary"}
            className="text-[10px] uppercase px-1.5 py-0 shrink-0"
          >
            {question.type === "ordinal" ? "Ordinal" : "Free\u00A0Text"}
          </Badge>
        </div>
        <span className="relative inline-grid items-center min-w-[60px]">
          <span className="invisible col-start-1 row-start-1 whitespace-pre px-1.5 pr-4 text-sm font-medium">
            {question.name || "Untitled"}
          </span>
          <Input
            className="col-start-1 row-start-1 h-7 w-full border-transparent bg-transparent px-1.5 text-sm font-medium text-foreground shadow-none hover:border-border hover:bg-muted/50 focus-visible:border-border focus-visible:bg-background focus-visible:ring-1 focus-visible:ring-ring"
            value={question.name}
            placeholder="e.g. Does this image show {{label}}?"
            onChange={(e) => updateField("name", e.target.value)}
            disabled={disabled}
          />
        </span>
        <div className="ml-auto flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={onMoveUp}
            disabled={disabled || index === 0}
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={onMoveDown}
            disabled={disabled || index === total - 1}
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 hover:text-destructive"
            onClick={onDelete}
            disabled={disabled}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setExpanded(!expanded)}
          >
            <ChevronRight className={cn("h-3.5 w-3.5 transition-transform duration-200", expanded && "rotate-90")} />
          </Button>
        </div>
      </div>

      {/* Expanded details — CSS grid-template-rows animation */}
      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-200 ease-out",
          expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="overflow-hidden min-h-0">
          <div className="border-t border-border px-3 py-3 space-y-3">
            <div className="space-y-1">
              <Label className="text-sm">Description (optional)</Label>
              <div className="pl-4">
                <Input
                  className="h-8 text-sm bg-background"
                  value={question.description ?? ""}
                  onChange={(e) => updateField("description", e.target.value)}
                  disabled={disabled}
                  placeholder="Optional help text. Example: Focus on the {{source_name}} region."
                />
              </div>
            </div>

            {question.type === "ordinal" && (
              <>
                <div className="pl-4 flex gap-3 items-end">
                  <div className="space-y-1 w-20">
                    <Label className="text-sm">Min Score</Label>
                    <Input
                      className={cn("h-8 text-sm bg-background", (question.min ?? 0) >= (question.max ?? 5) && "border-destructive")}
                      type="number"
                      value={question.min ?? 0}
                      onChange={(e) => handleMinMaxChange("min", e.target.value)}
                      disabled={disabled}
                    />
                  </div>
                  <div className="space-y-1 w-20">
                    <Label className="text-sm">Max Score</Label>
                    <Input
                      className={cn("h-8 text-sm bg-background", (question.min ?? 0) >= (question.max ?? 5) && "border-destructive")}
                      type="number"
                      value={question.max ?? 5}
                      onChange={(e) => handleMinMaxChange("max", e.target.value)}
                      disabled={disabled}
                    />
                  </div>
                  {(question.min ?? 0) >= (question.max ?? 5) && (
                    <span className="text-xs text-destructive pb-2">Min must be less than max</span>
                  )}
                </div>

                <div className="space-y-1">
                  <Label className="text-sm">Score Labels</Label>
                  <div className="pl-4 flex flex-wrap gap-2">
                    {scoreRange.map((score) => (
                      <div key={score} className="flex items-stretch rounded-md border border-border overflow-hidden">
                        <span className="flex items-center bg-muted px-2 text-xs font-medium text-muted-foreground border-r border-border">
                          {score}
                        </span>
                        <Input
                          className="h-8 w-28 border-0 rounded-none text-sm bg-background focus-visible:ring-0 focus-visible:ring-offset-0"
                          value={question.labels?.[String(score)] ?? ""}
                          onChange={(e) =>
                            handleLabelChange(String(score), e.target.value)
                          }
                          disabled={disabled}
                          placeholder={`Label for ${score}`}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
