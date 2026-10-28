import { useState, useCallback, useMemo, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import type { DragEndEvent } from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { restrictToVerticalAxis } from "@dnd-kit/modifiers";
import {
  Plus,
  Save,
  RotateCcw,
  Eye,
  EyeOff,
  X,
} from "lucide-react";
import type {
  Study,
  RatingSchema,
  SchemaQuestion,
  FailureReasonConfig,
  AttributeSchema,
  PaginatedBrowse,
} from "@/types";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { QuestionCard } from "@/components/schema-builder/question-card";
import { SchemaPreview } from "@/components/schema-builder/schema-preview";
import {
  extractSchemaQuestionPlaceholderNames,
  formatAttributePlaceholder,
} from "@/lib/question-placeholders";

interface SchemaTabProps {
  study: Study;
  onDirtyChange?: (dirty: boolean) => void;
  saveRef?: React.MutableRefObject<(() => Promise<void>) | null>;
}

function generateId(): string {
  return `q_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

const OPERATORS = ["<=", "<", "==", ">=", ">"] as const;

export default function SchemaTab({ study, onDirtyChange, saveRef }: SchemaTabProps) {
  const queryClient = useQueryClient();
  const studyId = study.id;

  // Normalize server schema into the local shape (filling in defaults)
  function normalizeSchema(s: RatingSchema): RatingSchema {
    return {
      questions: s.questions ?? [],
      failure_reason: s.failure_reason ?? {
        enabled: false,
        label: "Failure Reason",
        options: [],
        multi_select: false,
      },
      visible_attributes: s.visible_attributes ?? [],
    };
  }

  // Local editable copy of the schema
  const [schema, setSchema] = useState<RatingSchema>(() =>
    normalizeSchema(study.rating_schema),
  );

  // Track the *local-shaped* snapshot at the time we last synced
  const [lastSyncedJson, setLastSyncedJson] = useState(
    JSON.stringify(normalizeSchema(study.rating_schema)),
  );

  useEffect(() => {
    const normalized = normalizeSchema(study.rating_schema);
    const serverLocalJson = JSON.stringify(normalized);
    const localJson = JSON.stringify(schema);
    // If server changed AND local state still matches the old server state -> sync
    if (serverLocalJson !== lastSyncedJson && localJson === lastSyncedJson) {
      const timeoutId = window.setTimeout(() => {
        setSchema(normalized);
        setLastSyncedJson(serverLocalJson);
      }, 0);
      return () => window.clearTimeout(timeoutId);
    }
    return undefined;
  }, [study.rating_schema, schema, lastSyncedJson]);

  const [uncertaintyEnabled, setUncertaintyEnabled] = useState(
    study.uncertainty_enabled
  );
  const [previewOpen, setPreviewOpen] = useState(false);

  // Dirty tracking — compare local state against last synced snapshot
  const isDirty = useMemo(
    () =>
      JSON.stringify(schema) !== lastSyncedJson ||
      uncertaintyEnabled !== study.uncertainty_enabled,
    [schema, lastSyncedJson, uncertaintyEnabled, study.uncertainty_enabled],
  );

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [leavingIds, setLeavingIds] = useState<Set<string>>(new Set());

  const isEditable = study.status === 'draft';

  // Fetch available attribute names from the dataset
  const datasetName = study.dataset_name;
  const attributesQuery = useQuery<AttributeSchema[]>({
    queryKey: ["admin", "datasets", datasetName, "attributes"],
    queryFn: () =>
      api.get<AttributeSchema[]>(
        `/api/admin/datasets/${datasetName}/attributes`,
      ),
    enabled: !!datasetName,
  });

  const availableAttributeNames = useMemo(
    () => (attributesQuery.data ?? []).map((a) => a.name),
    [attributesQuery.data],
  );
  const referencedPlaceholderNames = useMemo(
    () => extractSchemaQuestionPlaceholderNames(schema.questions ?? []),
    [schema.questions],
  );
  const unknownPlaceholderNames = useMemo(
    () =>
      referencedPlaceholderNames.filter(
        (name) => !availableAttributeNames.includes(name),
      ),
    [availableAttributeNames, referencedPlaceholderNames],
  );
  const previewSampleQuery = useQuery<{
    imageName: string;
    attributes: Record<string, string | number | boolean>;
  } | null>({
    queryKey: ["admin", "datasets", datasetName, "question-preview-sample"],
    queryFn: async () => {
      if (!datasetName) return null;

      const data = await api.get<PaginatedBrowse>(
        `/api/admin/datasets/${encodeURIComponent(datasetName)}/images?page=1&per_page=1`,
      );
      const sample = data.items[0];
      if (!sample) return null;

      return {
        imageName: sample.image_name,
        attributes: sample.attributes,
      };
    },
    enabled: Boolean(datasetName),
  });

  // dnd-kit sensors with distance constraint to prevent accidental drags
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  );

  const questionIds = useMemo(
    () => schema.questions.map((q) => q.id),
    [schema.questions],
  );

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setSchema((prev) => {
      const oldIndex = prev.questions.findIndex((q) => q.id === active.id);
      const newIndex = prev.questions.findIndex((q) => q.id === over.id);
      if (oldIndex === -1 || newIndex === -1) return prev;
      return { ...prev, questions: arrayMove(prev.questions, oldIndex, newIndex) };
    });
  }, []);

  // --- Mutations ---

  const saveMutation = useMutation({
    mutationFn: () =>
      api.put<{ message: string }>(
        `/api/admin/studies/${studyId}/schema`,
        { schema },
      ),
    onSuccess: async () => {
      // Also save uncertainty setting alongside schema
      try {
        await api.put(`/api/admin/studies/${studyId}/settings`, {
          uncertainty_enabled: uncertaintyEnabled,
        });
      } catch {
        toast.error("Failed to save uncertainty setting");
      }
      toast.success("Schema saved successfully");
      setLastSyncedJson(JSON.stringify(schema));
      queryClient.invalidateQueries({
        queryKey: ["admin", "studies", String(studyId)],
      });
    },
    onError: (err: Error) => {
      toast.error(`Failed to save schema: ${err.message}`);
    },
  });

  // Save ref for unsaved-changes warning
  const handleSchemaSave = useCallback(async () => {
    await saveMutation.mutateAsync();
  }, [saveMutation]);

  useEffect(() => {
    if (saveRef) saveRef.current = handleSchemaSave;
    return () => { if (saveRef) saveRef.current = null; };
  }, [saveRef, handleSchemaSave]);

  const resetMutation = useMutation({
    mutationFn: () =>
      api.post<{ rating_schema: RatingSchema }>(
        `/api/admin/studies/${studyId}/schema/reset`,
      ),
    onSuccess: (data) => {
      const normalized = normalizeSchema(data.rating_schema);
      setSchema(normalized);
      setValidationErrors([]);
      setLastSyncedJson(JSON.stringify(normalized));
      toast.success("Schema reset to defaults");
      queryClient.invalidateQueries({
        queryKey: ["admin", "studies", String(studyId)],
      });
    },
    onError: (err: Error) => {
      toast.error(`Failed to reset schema: ${err.message}`);
    },
  });

  // --- Question operations ---

  const updateQuestion = useCallback(
    (index: number, updated: SchemaQuestion) => {
      setSchema((prev) => {
        const questions = [...prev.questions];
        questions[index] = updated;
        return { ...prev, questions };
      });
    },
    [],
  );

  const deleteQuestion = useCallback((id: string) => {
    setLeavingIds((prev) => new Set(prev).add(id));
    setTimeout(() => {
      setSchema((prev) => ({
        ...prev,
        questions: prev.questions.filter((q) => q.id !== id),
      }));
      setLeavingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }, 150);
  }, []);

  const moveQuestion = useCallback((index: number, direction: -1 | 1) => {
    setSchema((prev) => {
      const questions = [...prev.questions];
      const target = index + direction;
      if (target < 0 || target >= questions.length) return prev;
      [questions[index], questions[target]] = [questions[target], questions[index]];
      return { ...prev, questions };
    });
  }, []);

  function addQuestion(type: "ordinal" | "free_text") {
    const newQ: SchemaQuestion = {
      id: generateId(),
      type,
      name: "",
      description: "",
      ...(type === "ordinal"
        ? {
            min: 0,
            max: 5,
            labels: {
              "0": "",
              "1": "",
              "2": "",
              "3": "",
              "4": "",
              "5": "",
            },
          }
        : {}),
    };
    setSchema((prev) => ({
      ...prev,
      questions: [...prev.questions, newQ],
    }));
  }

  // --- Visible attributes operations ---

  function toggleVisibleAttribute(attrName: string) {
    setSchema((prev) => {
      const current = prev.visible_attributes ?? [];
      const next = current.includes(attrName)
        ? current.filter((a) => a !== attrName)
        : [...current, attrName];
      return { ...prev, visible_attributes: next };
    });
  }

  // --- Failure reason operations ---

  function updateFailureReason(updates: Partial<FailureReasonConfig>) {
    setSchema((prev) => ({
      ...prev,
      failure_reason: { ...prev.failure_reason!, ...updates },
    }));
  }

  function addFailureOption() {
    const fr = schema.failure_reason!;
    updateFailureReason({ options: [...fr.options, ""] });
  }

  function updateFailureOption(index: number, value: string) {
    const fr = schema.failure_reason!;
    const options = [...fr.options];
    options[index] = value;
    updateFailureReason({ options });
  }

  function removeFailureOption(index: number) {
    const fr = schema.failure_reason!;
    updateFailureReason({
      options: fr.options.filter((_, i) => i !== index),
    });
  }

  const hasInvalidRange = schema.questions.some(
    (q) => q.type === "ordinal" && (q.min ?? 0) >= (q.max ?? 5),
  );

  const failureReason = schema.failure_reason!;

  const hasEmptyFailureLabel =
    failureReason.enabled && !failureReason.label?.trim();
  const hasNoFailureOptions =
    failureReason.enabled && failureReason.options.length === 0;

  // Check if the failure reason trigger can ever fire given ordinal ranges
  const hasUnreachableTrigger = useMemo(() => {
    if (!failureReason.enabled || !failureReason.condition) return false;
    const { type, operator, value: threshold, question_id } = failureReason.condition;
    if (threshold === undefined) return false;

    const canMeet = (min: number, max: number): boolean => {
      switch (operator) {
        case "==": case "===": case "equals": return threshold >= min && threshold <= max;
        case "<=": case "less_than_or_equal": return min <= threshold;
        case "<": case "less_than": return min < threshold;
        case ">=": case "greater_than_or_equal": return max >= threshold;
        case ">": case "greater_than": return max > threshold;
        case "!=": case "!==": return max !== min || min !== threshold;
        default: return true;
      }
    };

    const ordinals = schema.questions.filter((q) => q.type === "ordinal");
    if (ordinals.length === 0) return true;

    if (type === "specific_question") {
      const q = ordinals.find((q) => q.id === question_id);
      if (!q) return true; // question not found — also a problem
      return !canMeet(q.min ?? 0, q.max ?? 5);
    }

    // any_ordinal: unreachable if NO ordinal question can meet it
    return !ordinals.some((q) => canMeet(q.min ?? 0, q.max ?? 5));
  }, [failureReason, schema.questions]);

  return (
    <div className="space-y-4">
      {/* Validation Errors */}
      {validationErrors.length > 0 && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-3 space-y-1">
          <p className="text-sm font-medium text-destructive">Validation Errors:</p>
          <ul className="text-sm text-destructive list-disc list-inside">
            {validationErrors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Questions Section */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Questions</CardTitle>
          <CardDescription className="text-sm">
            Define the questions shown to participants. Drag to reorder, enlarge to edit.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 pl-8">
          <div className="rounded-md border border-border/70 bg-muted/35 p-3 text-sm text-muted-foreground">
            <p>
              Question titles and descriptions can include dataset attributes with{" "}
              <code className="rounded bg-background px-1 py-0.5 font-mono text-xs">
                {formatAttributePlaceholder("label")}
              </code>.
              The value is replaced per image during evaluation.
            </p>
            <p className="mt-1">
              Examples:{" "}
              <code className="rounded bg-background px-1 py-0.5 font-mono text-xs">
                Does this image show {formatAttributePlaceholder("label")}?
              </code>{" "}
            </p>
            {availableAttributeNames.length > 0 && (
              <>
                <p className="mt-2">
                  Attributes available for {datasetName}:
                </p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {availableAttributeNames.map((name) => (
                    <code
                      key={name}
                      className="rounded bg-background px-1 py-0.5 font-mono text-xs text-foreground"
                    >
                      {formatAttributePlaceholder(name)}
                    </code>
                  ))}
                </div>
              </>
            )}
            {unknownPlaceholderNames.length > 0 && (
              <p className="mt-2 text-destructive">
                Unknown placeholders:{" "}
                {unknownPlaceholderNames
                  .map((name) => formatAttributePlaceholder(name))
                  .join(", ")}
              </p>
            )}
          </div>

          {schema.questions.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No questions defined yet. Add one below.
            </p>
          )}

          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            modifiers={[restrictToVerticalAxis]}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={questionIds} strategy={verticalListSortingStrategy}>
              {schema.questions.map((q, i) => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  index={i}
                  total={schema.questions.length}
                  disabled={!isEditable}
                  leaving={leavingIds.has(q.id)}
                  defaultExpanded={i === 0}
                  onChange={(updated) => updateQuestion(i, updated)}
                  onDelete={() => deleteQuestion(q.id)}
                  onMoveUp={() => moveQuestion(i, -1)}
                  onMoveDown={() => moveQuestion(i, 1)}
                />
              ))}
            </SortableContext>
          </DndContext>

          <div className="flex gap-2 pt-1">
            <Button
              variant="link"
              size="sm"
              className="px-0 text-xs"
              onClick={() => addQuestion("ordinal")}
              disabled={!isEditable}
            >
              <Plus className="h-3 w-3" />
              Add Ordinal Question
            </Button>
            <Button
              variant="link"
              size="sm"
              className="px-0 text-xs"
              onClick={() => addQuestion("free_text")}
              disabled={!isEditable}
            >
              <Plus className="h-3 w-3" />
              Add Free Text Question
            </Button>
          </div>

          {/* Uncertainty toggle */}
          <div className="flex items-center justify-between gap-2 pt-2">
            <div className="flex items-center gap-1.5 text-sm">
              <Label className="text-sm">Uncertainty</Label>
              <span className="text-muted-foreground/40">·</span>
              <span className="text-muted-foreground font-normal">If enabled, participants can indicate they are uncertain about an answer</span>
            </div>
            <Switch
              checked={uncertaintyEnabled}
              onCheckedChange={setUncertaintyEnabled}
              disabled={!isEditable}
              className="shrink-0"
            />
          </div>
        </CardContent>
      </Card>

      {/* Visible Attributes Section */}
      {datasetName && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Visible Attributes</CardTitle>
            <CardDescription className="text-sm">
              Select which dataset attributes are shown to participants during evaluation.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pl-8">
            {attributesQuery.isLoading && (
              <p className="text-xs text-muted-foreground">Loading attributes...</p>
            )}
            {!attributesQuery.isLoading && availableAttributeNames.length === 0 && (
              <p className="text-xs text-muted-foreground">
                No attributes available in dataset.
              </p>
            )}
            {availableAttributeNames.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {availableAttributeNames.map((attrName) => {
                  const isVisible = (schema.visible_attributes ?? []).includes(attrName);
                  return (
                    <button
                      key={attrName}
                      type="button"
                      onClick={() => toggleVisibleAttribute(attrName)}
                      disabled={!isEditable}
                      className={cn(
                        "flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm transition-colors",
                        isVisible
                          ? "border-primary/40 bg-primary/10 text-primary"
                          : "border-border bg-transparent text-muted-foreground hover:text-foreground hover:border-border/80",
                        !isEditable && "cursor-not-allowed opacity-50"
                      )}
                    >
                      {isVisible
                        ? <Eye className="size-3.5 shrink-0" />
                        : <EyeOff className="size-3.5 shrink-0" />}
                      {attrName}
                    </button>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Failure Reason Section */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Failure Reason</CardTitle>
              <CardDescription className="text-sm">
                If a certain rating falls below a threshold, ask participants why.
              </CardDescription>
            </div>
            <Switch
              checked={failureReason.enabled}
              onCheckedChange={(checked) =>
                updateFailureReason({
                  enabled: checked,
                  ...(checked && !failureReason.label?.trim()
                    ? { label: "Why did you rate this image so low?" }
                    : {}),
                })
              }
              disabled={!isEditable}
            />
          </div>
        </CardHeader>
        {failureReason.enabled && (
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <Label className="text-sm" htmlFor="fr-label">Label{hasEmptyFailureLabel && <span className="text-destructive"> *</span>}</Label>
              <div className="pl-4">
                <Input
                  id="fr-label"
                  className={cn("h-8 text-sm", hasEmptyFailureLabel && "border-destructive")}
                  value={failureReason.label}
                  onChange={(e) => updateFailureReason({ label: e.target.value })}
                  disabled={!isEditable}
                  placeholder="e.g. What is the reason for your low rating?"
                />
                {hasEmptyFailureLabel && (
                  <p className="text-xs text-destructive mt-1">Label is required.</p>
                )}
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-sm">Options{hasNoFailureOptions && <span className="text-destructive"> *</span>}</Label>
              <div className="pl-4 flex flex-wrap gap-2">
                {failureReason.options.map((opt, i) => (
                  <div key={i} className="flex items-stretch rounded-md border border-border overflow-hidden">
                    <span className="relative inline-grid items-center min-w-[80px]">
                      <span className="invisible col-start-1 row-start-1 whitespace-pre px-3 pr-5 text-sm">
                        {opt || `Option ${i + 1}`}
                      </span>
                      <Input
                        className="col-start-1 row-start-1 h-8 w-full border-0 rounded-none text-sm focus-visible:ring-0 focus-visible:ring-offset-0"
                        value={opt}
                        onChange={(e) => updateFailureOption(i, e.target.value)}
                        disabled={!isEditable}
                        placeholder={`Option ${i + 1}`}
                      />
                    </span>
                    <button
                      className="flex items-center px-1.5 text-muted-foreground hover:text-destructive hover:bg-muted/50 border-l border-border"
                      onClick={() => removeFailureOption(i)}
                      disabled={!isEditable}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs gap-1"
                  onClick={addFailureOption}
                  disabled={!isEditable}
                >
                  <Plus className="h-3 w-3" />
                  Add
                </Button>
              {hasNoFailureOptions && (
                <p className="text-xs text-destructive">At least one option is required.</p>
              )}
              </div>
            </div>

            <div className="pl-4 flex items-center gap-2">
              <Label className="text-sm" htmlFor="fr-multi">Allow multi-select</Label>
              <Switch
                id="fr-multi"
                checked={failureReason.multi_select}
                onCheckedChange={(checked) =>
                  updateFailureReason({ multi_select: checked })
                }
                disabled={!isEditable}
              />
            </div>

            <div className="space-y-1">
              <div className="flex items-center gap-1.5 text-sm">
                <Label className="text-sm">Conditional Trigger</Label>
                <span className="text-muted-foreground/40">·</span>
                <span className="text-muted-foreground font-normal">When this condition is met, the failure reason field appears</span>
              </div>
              <div className="pl-4">
              <div className="flex items-stretch rounded-md border border-border overflow-hidden w-fit">
                <Select
                  value={failureReason.condition?.type ?? "any_ordinal"}
                  onValueChange={(val) => {
                    const base = {
                      type: val as "any_ordinal" | "specific_question",
                      operator: failureReason.condition?.operator ?? "<=",
                      value: failureReason.condition?.value ?? 0,
                    };
                    if (val === "specific_question") {
                      const firstOrdinal = schema.questions.find((q) => q.type === "ordinal");
                      updateFailureReason({
                        condition: {
                          ...base,
                          question_id: failureReason.condition?.question_id || firstOrdinal?.id || "",
                        },
                      });
                    } else {
                      updateFailureReason({ condition: base });
                    }
                  }}
                  disabled={!isEditable}
                >
                  <SelectTrigger className="h-8 text-xs w-auto border-0 rounded-none shadow-none focus:ring-0">
                    <SelectValue placeholder="Type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any_ordinal">Any ordinal question</SelectItem>
                    <SelectItem value="specific_question">Specific question</SelectItem>
                  </SelectContent>
                </Select>

                {(failureReason.condition?.type ?? "any_ordinal") === "specific_question" && (
                  <>
                    <div className="w-px bg-border shrink-0" />
                    <Select
                      value={failureReason.condition?.question_id ?? ""}
                      onValueChange={(val) =>
                        updateFailureReason({
                          condition: {
                            type: "specific_question",
                            question_id: val,
                            operator: failureReason.condition?.operator ?? "<=",
                            value: failureReason.condition?.value ?? 0,
                          },
                        })
                      }
                      disabled={!isEditable}
                    >
                      <SelectTrigger className="h-8 text-xs w-auto border-0 rounded-none shadow-none focus:ring-0">
                        <SelectValue placeholder="Question" />
                      </SelectTrigger>
                      <SelectContent>
                        {schema.questions
                          .filter((q) => q.type === "ordinal")
                          .map((q) => (
                            <SelectItem key={q.id} value={q.id}>
                              {q.name || q.id}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </>
                )}

                <div className="w-px bg-border shrink-0" />

                <Select
                  value={failureReason.condition?.operator ?? "<="}
                  onValueChange={(val) => {
                    const condType = failureReason.condition?.type ?? "any_ordinal";
                    const base = {
                      type: condType,
                      operator: val,
                      value: failureReason.condition?.value ?? 0,
                    };
                    if (condType === "specific_question") {
                      updateFailureReason({
                        condition: {
                          ...base,
                          question_id: failureReason.condition?.question_id ?? "",
                        },
                      });
                    } else {
                      updateFailureReason({ condition: base });
                    }
                  }}
                  disabled={!isEditable}
                >
                  <SelectTrigger className="h-8 text-xs w-auto border-0 rounded-none shadow-none focus:ring-0">
                    <SelectValue placeholder="Op" />
                  </SelectTrigger>
                  <SelectContent>
                    {OPERATORS.map((op) => (
                      <SelectItem key={op} value={op}>
                        {op}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <div className="w-px bg-border shrink-0" />

                <Input
                  type="number"
                  className="h-8 text-xs w-16 border-0 rounded-none shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                  value={failureReason.condition?.value ?? 0}
                  onChange={(e) => {
                    const num = parseInt(e.target.value, 10);
                    if (isNaN(num)) return;
                    const condType = failureReason.condition?.type ?? "any_ordinal";
                    const base = {
                      type: condType,
                      operator: failureReason.condition?.operator ?? "<=",
                      value: num,
                    };
                    if (condType === "specific_question") {
                      updateFailureReason({
                        condition: {
                          ...base,
                          question_id: failureReason.condition?.question_id ?? "",
                        },
                      });
                    } else {
                      updateFailureReason({ condition: base });
                    }
                  }}
                  disabled={!isEditable}
                  placeholder="Value"
                />
              </div>
              {hasUnreachableTrigger && (
                <p className="text-xs text-destructive mt-1">This condition can never be met with the current question ranges.</p>
              )}
              </div>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Action Buttons */}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending || hasInvalidRange || hasEmptyFailureLabel || hasNoFailureOptions || hasUnreachableTrigger}
        >
          <Save className="h-3.5 w-3.5" />
          {saveMutation.isPending ? "Saving..." : "Save Questions"}
        </Button>

        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="outline" size="sm" disabled={!isEditable}>
              <RotateCcw className="h-3.5 w-3.5" />
              Reset to Defaults
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Reset Schema?</AlertDialogTitle>
              <AlertDialogDescription>
                This will discard all changes and reset the schema to its
                default configuration. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                variant="destructive"
                onClick={() => resetMutation.mutate()}
              >
                Reset
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <Button variant="outline" size="sm" onClick={() => setPreviewOpen(true)}>
          <Eye className="h-3.5 w-3.5" />
          Preview
        </Button>
      </div>

      {/* Preview Dialog */}
      <SchemaPreview
        schema={schema}
        uncertaintyEnabled={uncertaintyEnabled}
        previewAttributes={previewSampleQuery.data?.attributes}
        previewImageName={previewSampleQuery.data?.imageName}
        open={previewOpen}
        onOpenChange={setPreviewOpen}
      />
    </div>
  );
}
