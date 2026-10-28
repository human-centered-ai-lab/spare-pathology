import { useCallback, useMemo } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FailureReasonConfig } from "@/types";

interface FailureReasonProps {
  config: FailureReasonConfig;
  value: string | string[] | null;
  onSave: (value: string | string[] | null) => void;
  readOnly: boolean;
}

export function FailureReason({
  config,
  value,
  onSave,
  readOnly,
}: FailureReasonProps) {
  const selectedValues: string[] = useMemo(
    () =>
      Array.isArray(value)
        ? value
        : value
          ? [value]
          : [],
    [value],
  );

  const handleToggle = useCallback(
    (option: string) => {
      if (readOnly) return;

      if (config.multi_select) {
        const current = [...selectedValues];
        const idx = current.indexOf(option);
        if (idx >= 0) {
          current.splice(idx, 1);
          onSave(current.length > 0 ? current : null);
        } else {
          current.push(option);
          onSave(current);
        }
      } else {
        // Single select: toggle
        if (selectedValues.includes(option)) {
          onSave(null);
        } else {
          onSave(option);
        }
      }
    },
    [config.multi_select, selectedValues, onSave, readOnly],
  );

  const helperText = config.multi_select
    ? "Select all reasons that apply."
    : "Select one reason.";

  return (
    <div className="space-y-2.5 rounded-md px-2 py-1.5 -mx-2">
      <div className="space-y-0.5">
        <p className="text-xs font-medium text-foreground">{config.label}</p>
        <p className="text-[11px] text-muted-foreground">{helperText}</p>
      </div>

      <div className="space-y-2">
        {config.options.map((option) => {
          const isSelected = selectedValues.includes(option);

          return (
            <button
              key={option}
              type="button"
              role={config.multi_select ? "checkbox" : "radio"}
              aria-checked={isSelected}
              disabled={readOnly}
              onClick={() => handleToggle(option)}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors",
                isSelected
                  ? "border-primary bg-primary/5 text-foreground"
                  : "border-border bg-background hover:bg-accent hover:text-foreground",
                readOnly && "cursor-default",
              )}
            >
              <span
                className={cn(
                  "flex size-4 shrink-0 items-center justify-center border",
                  config.multi_select ? "rounded-[4px]" : "rounded-full",
                  isSelected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-muted-foreground/30 bg-background text-transparent",
                )}
              >
                {config.multi_select ? (
                  <Check className="size-3" />
                ) : (
                  <span
                    className={cn(
                      "size-1.5 rounded-full",
                      isSelected ? "bg-primary-foreground" : "bg-transparent",
                    )}
                  />
                )}
              </span>
              <span className="min-w-0 flex-1">{option}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
