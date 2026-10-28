import type { RatingSchema } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  extractSchemaQuestionPlaceholderNames,
  formatAttributePlaceholder,
  renderQuestionTemplate,
} from "@/lib/question-placeholders";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface SchemaPreviewProps {
  schema: RatingSchema;
  uncertaintyEnabled: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  previewAttributes?: Record<string, string | number | boolean>;
  previewImageName?: string | null;
}

export function SchemaPreview({
  schema,
  uncertaintyEnabled,
  open,
  onOpenChange,
  previewAttributes,
  previewImageName,
}: SchemaPreviewProps) {
  const placeholderNames = extractSchemaQuestionPlaceholderNames(schema.questions ?? []);
  const previewSubstitutions = placeholderNames
    .map((name) => ({
      name,
      value: previewAttributes?.[name],
    }))
    .filter(
      (
        entry,
      ): entry is {
        name: string;
        value: string | number | boolean;
      } => entry.value !== undefined && entry.value !== null,
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Question Preview</DialogTitle>
          <DialogDescription>
            Preview of the questions as participants will see them.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {placeholderNames.length > 0 && (
            <div className="rounded-md border border-border/70 bg-muted/35 p-3 text-xs text-muted-foreground">
              <p>
                Attribute placeholders use the <code className="rounded bg-background px-1 py-0.5 font-mono text-[11px]">{formatAttributePlaceholder("attribute_name")}</code> syntax.
                {previewImageName ? ` Previewing with values from ${previewImageName}.` : ""}
              </p>
              {previewSubstitutions.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {previewSubstitutions.map(({ name, value }) => (
                    <Badge key={name} variant="outline" className="font-normal">
                      <span className="font-mono text-[11px]">{formatAttributePlaceholder(name)}</span>
                      <span className="mx-1 text-muted-foreground">=</span>
                      <span>{renderQuestionTemplate(formatAttributePlaceholder(name), { [name]: value })}</span>
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="mt-2">
                  No sample image values are available yet, so unresolved placeholders stay visible in this preview.
                </p>
              )}
            </div>
          )}

          {schema.questions.map((q, idx) => (
            <div key={q.id} className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-muted-foreground">
                  {idx + 1}.
                </span>
                <Label className="text-sm font-medium">
                  {renderQuestionTemplate(q.name, previewAttributes)}
                </Label>
                <Badge
                  variant={q.type === "ordinal" ? "default" : "secondary"}
                >
                  {q.type}
                </Badge>
              </div>

              {q.description && (
                <p className="text-sm text-muted-foreground ml-5">
                  {renderQuestionTemplate(q.description, previewAttributes)}
                </p>
              )}

              {q.type === "ordinal" && (
                <div className="ml-5 space-y-1">
                  <div className="flex gap-2 flex-wrap">
                    {Object.entries(q.labels ?? {}).map(([score, label]) => (
                      <div
                        key={score}
                        className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm"
                      >
                        <span className="font-mono font-medium">{score}</span>
                        {label && (
                          <>
                            <span className="text-muted-foreground">-</span>
                            <span className="text-muted-foreground">{label}</span>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {q.type === "free_text" && (
                <div className="ml-5">
                  <Textarea disabled placeholder="Enter response..." rows={2} />
                </div>
              )}

            </div>
          ))}

          {schema.failure_reason?.enabled && (
            <>
              <div className="space-y-2">
                <Label className="text-sm font-medium">
                  {schema.failure_reason.label || "Failure Reason"}
                </Label>
                {schema.failure_reason.condition && (
                  <p className="text-xs text-muted-foreground">
                    Appears when{" "}
                    {schema.failure_reason.condition.type === "any_ordinal" ? (
                      <>any ordinal question</>
                    ) : (
                      <code className="bg-muted px-1 rounded">
                        {schema.failure_reason.condition.question_id}
                      </code>
                    )}{" "}
                    {schema.failure_reason.condition.operator}{" "}
                    {schema.failure_reason.condition.value}
                  </p>
                )}
                <div className="ml-5 space-y-1.5">
                  {schema.failure_reason.options.map((option) => (
                    <div key={option} className="flex items-center gap-2">
                      <Checkbox disabled />
                      <span className="text-sm">{option}</span>
                    </div>
                  ))}
                </div>
                {schema.failure_reason.multi_select && (
                  <p className="text-xs text-muted-foreground ml-5">
                    Multiple selections allowed
                  </p>
                )}
              </div>
            </>
          )}

          {uncertaintyEnabled && (
            <div className="flex items-center gap-2.5 px-3 py-2.5">
              <Checkbox disabled />
              <span className="text-sm text-foreground leading-tight">
                I am uncertain about this rating
              </span>
            </div>
          )}

        </div>

        <DialogFooter showCloseButton />
      </DialogContent>
    </Dialog>
  );
}
