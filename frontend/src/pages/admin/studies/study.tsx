import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Lock,
  LockOpen,
  Settings,
  ListChecks,
  Images,
  Users,
  BarChart3,
  Download,
  CheckCircle2,
  XCircle,
  Save,
  Trash2,
  X,
  Rocket,
} from "lucide-react";
import { toast } from "sonner";
import { useAdminStudy } from "@/hooks/use-admin-studies";
import { api } from "@/api/client";
import type { Study } from "@/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import SettingsTab from "./settings-tab";
import SchemaTab from "./schema-tab";
import DatasetTab from "./dataset-tab";
import { ParticipantsTab } from "./participants-tab";
import { EvaluationTab } from "./evaluation-tab";
import { ExportTab } from "./export-tab";

const TABS = [
  { value: "settings", label: "General", icon: Settings },
  { value: "schema", label: "Questions", icon: ListChecks },
  { value: "dataset", label: "Images", icon: Images },
  { value: "participants", label: "Participants", icon: Users },
  { value: "evaluation", label: "Evaluation", icon: BarChart3 },
  { value: "export", label: "Export", icon: Download },
] as const;

type TabValue = (typeof TABS)[number]["value"];

function isValidTab(value: string | undefined): value is TabValue {
  return TABS.some((t) => t.value === value);
}

export default function StudyPage() {
  const { studyId, tab } = useParams<{
    studyId: string;
    tab: string;
  }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isNew = studyId === "new";

  // Readiness state
  const [readiness, setReadiness] = useState<
    { id: string; label: string; ready: boolean }[] | null
  >(null);
  const [showActivateConfirm, setShowActivateConfirm] = useState(false);
  const [showRevertConfirm, setShowRevertConfirm] = useState(false);

  // Unsaved changes tracking
  const [settingsDirty, setSettingsDirty] = useState(false);
  const [schemaDirty, setSchemaDirty] = useState(false);
  const [pendingTab, setPendingTab] = useState<string | null>(null);
  const settingsSaveRef = useRef<(() => Promise<void>) | null>(null);
  const schemaSaveRef = useRef<(() => Promise<void>) | null>(null);

  // Create study and redirect when visiting /admin/studies/new
  useEffect(() => {
    if (!isNew) return;
    let cancelled = false;
    api
      .post<Study>("/api/admin/studies", {})
      .then((data) => {
        if (cancelled) return;
        queryClient.invalidateQueries({ queryKey: ["admin", "studies"] });
        navigate(`/admin/studies/${data.id}/settings`, {
          replace: true,
        });
      })
      .catch(() => {
        if (cancelled) return;
        toast.error("Failed to create study.");
        navigate("/admin/studies", { replace: true });
      });
    return () => { cancelled = true; };
  }, [isNew, navigate, queryClient]);

  const { data: study, isLoading } = useAdminStudy(
    isNew ? "0" : (studyId ?? "0"),
  );

  const activeTab: TabValue = isValidTab(tab) ? tab : "settings";

  const currentTabDirty =
    (activeTab === "settings" && settingsDirty) ||
    (activeTab === "schema" && schemaDirty);

  const handleTabChange = (value: string) => {
    if (currentTabDirty) {
      setPendingTab(value);
      return;
    }
    navigate(`/admin/studies/${studyId}/${value}`);
  };

  const handleDiscardAndNavigate = useCallback(() => {
    if (!pendingTab) return;
    const dest = pendingTab;
    setPendingTab(null);
    navigate(`/admin/studies/${studyId}/${dest}`);
  }, [pendingTab, studyId, navigate]);

  const handleSaveAndNavigate = useCallback(async () => {
    if (!pendingTab) return;
    const dest = pendingTab;
    const ref = activeTab === "settings" ? settingsSaveRef : schemaSaveRef;
    try {
      await ref.current?.();
    } catch {
      // save failed — stay on current tab
      setPendingTab(null);
      return;
    }
    setPendingTab(null);
    navigate(`/admin/studies/${studyId}/${dest}`);
  }, [pendingTab, activeTab, studyId, navigate]);

  const invalidateStudy = () => {
    queryClient.invalidateQueries({
      queryKey: ["admin", "studies", String(studyId)],
    });
    queryClient.invalidateQueries({ queryKey: ["admin", "studies"] });
    // Refresh the activation checklist
    fetchReadiness();
  };

  const reopenStudy = useMutation({
    mutationFn: () =>
      api.post<{ deleted_ratings: number }>(`/api/admin/studies/${studyId}/reopen`),
    onSuccess: (data) => {
      toast.success(
        `Study reverted to draft. ${data.deleted_ratings} rating(s) deleted.`
      );
      invalidateStudy();
    },
    onError: () => {
      toast.error("Failed to revert study to draft.");
    },
  });

  const activateStudy = useMutation({
    mutationFn: () =>
      api.post(`/api/admin/studies/${studyId}/activate`),
    onSuccess: () => {
      toast.success("Study activated.");
      invalidateStudy();
    },
    onError: () => {
      toast.error("Failed to activate study. Check readiness requirements.");
    },
  });

  const fetchReadiness = useCallback(async () => {
    try {
      const data = await api.get<{
        checklist: { id: string; label: string; ready: boolean }[];
        all_ready: boolean;
      }>(`/api/admin/studies/${studyId}/readiness`);
      setReadiness(data.checklist);
    } catch {
      // silently fail for auto-fetch
    }
  }, [studyId]);

  // Auto-fetch readiness checklist for draft studies
  // Re-fetch on tab switch to pick up changes from schema/dataset/participant tabs
  useEffect(() => {
    if (study?.status === "draft") {
      void fetchReadiness();
    }
  }, [study?.status, activeTab, fetchReadiness]);

  const visibleReadiness = study?.status === "draft" ? readiness : null;

  const handleNameBlur = (e: React.FocusEvent<HTMLHeadingElement>) => {
    const newName = e.currentTarget.textContent?.trim();
    if (newName && newName !== study?.name) {
      api
        .put(`/api/admin/studies/${studyId}/settings`, {
          name: newName,
        })
        .then(() => {
          toast.success("Study name updated.");
          invalidateStudy();
        })
        .catch(() => {
          toast.error("Failed to update study name.");
        });
    }
  };

  if (isNew || isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (!study) {
    return (
      <div>
        <p className="text-muted-foreground">Study not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with inline-editable name + status controls */}
      <div className="mb-6 flex items-center gap-3">
        <h1
          className="text-2xl font-bold text-foreground cursor-text rounded px-2 py-1 -mx-2 border border-transparent hover:border-border hover:bg-muted/50 focus:outline-none focus:border-border focus:bg-background focus:ring-1 focus:ring-ring leading-none"
          contentEditable
          suppressContentEditableWarning
          onBlur={handleNameBlur}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              e.currentTarget.blur();
            }
          }}
        >
          {study.name}
        </h1>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Study Status:</span>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <button className="flex cursor-default items-center gap-1.5 rounded px-1 py-0.5 hover:bg-muted/60">
                  <span
                    className={cn(
                      "flex h-2 w-2 rounded-full",
                      study.status === "finished"
                        ? "bg-success"
                        : study.status === "active"
                          ? "bg-warning"
                          : "bg-muted-foreground/50"
                    )}
                  />
                  <span className="text-sm font-medium text-foreground capitalize">
                    {study.status}
                  </span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" align="end" className="max-w-xs p-4 text-left">
                <div className="space-y-3 text-xs">
                  <div className="space-y-0.5">
                    <p className="font-semibold flex items-center gap-1.5">
                      <span className="flex h-2 w-2 rounded-full bg-muted-foreground/50 shrink-0" />
                      Draft
                    </p>
                    <p className="opacity-70 leading-relaxed pl-3.5">
                      Fully editable. Configure schema, dataset, and participants freely.
                      Participants cannot see or access the study yet.
                    </p>
                  </div>
                  <div className="space-y-0.5">
                    <p className="font-semibold flex items-center gap-1.5">
                      <span className="flex h-2 w-2 rounded-full bg-warning shrink-0" />
                      Active
                    </p>
                    <p className="opacity-70 leading-relaxed pl-3.5">
                      Open to participants. Evaluations can be submitted.
                      Schema and dataset are frozen. Reverting to draft will
                      permanently delete all evaluation data.
                    </p>
                  </div>
                  <div className="space-y-0.5">
                    <p className="font-semibold flex items-center gap-1.5">
                      <span className="flex h-2 w-2 rounded-full bg-success shrink-0" />
                      Finished
                    </p>
                    <p className="opacity-70 leading-relaxed pl-3.5">
                      All participants submitted. Permanently locked.
                    </p>
                  </div>
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          {study.status === "draft" ? (() => {
            const allReady = visibleReadiness != null && visibleReadiness.length > 0 && visibleReadiness.every((c) => c.ready);
            const failingItems = visibleReadiness?.filter((c) => !c.ready) ?? [];
            const btn = (
              <Button
                size="sm"
                className="ml-2"
                onClick={() => setShowActivateConfirm(true)}
                disabled={!allReady || activateStudy.isPending}
              >
                <Rocket className="size-4 mr-1.5" />
                Activate
              </Button>
            );
            return !allReady && failingItems.length > 0 ? (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="inline-flex">{btn}</span>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" align="end" className="max-w-xs p-3">
                    <p className="text-xs font-medium mb-1">Cannot activate yet:</p>
                    <ul className="text-xs space-y-0.5">
                      {failingItems.map((c) => (
                        <li key={c.id} className="flex items-center gap-1.5">
                          <XCircle className="size-3 text-destructive shrink-0" />
                          {c.label}
                        </li>
                      ))}
                    </ul>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            ) : btn;
          })() : null}
        </div>
      </div>

      {/* Checklist to activate study */}
      {visibleReadiness && (
        <div className="rounded-md border p-4 space-y-2">
          <p className="text-sm font-medium">Checklist to activate study:</p>
          {visibleReadiness.map((check) => (
            <div key={check.id} className="flex items-center gap-2 text-sm">
              {check.ready ? (
                <CheckCircle2 className="size-4 text-success" />
              ) : (
                <XCircle className="size-4 text-destructive" />
              )}
              <span
                className={check.ready ? "" : "text-muted-foreground"}
              >
                {check.label}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Activate Confirmation Dialog */}
      <Dialog open={showActivateConfirm} onOpenChange={setShowActivateConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Activate study?</DialogTitle>
            <DialogDescription>
              Activating this study will allow participants to access it and
              will freeze schema and dataset edits. You can change it back to draft
              later if needed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowActivateConfirm(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={() => {
                setShowActivateConfirm(false);
                activateStudy.mutate();
              }}
              disabled={activateStudy.isPending}
            >
              <Rocket className="size-4 mr-1.5" />
              Activate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revert to Draft Confirmation Dialog */}
      <AlertDialog open={showRevertConfirm} onOpenChange={setShowRevertConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revert study to draft?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete all evaluation data (ratings,
              submission progress, and time tracking). This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                setShowRevertConfirm(false);
                reopenStudy.mutate();
              }}
            >
              Revert to Draft
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Frozen Banner */}
      {study.status === "finished" && (
        <div className="flex items-center gap-3 rounded-md border border-success/50 bg-success/10 p-4">
          <Lock className="size-5 text-success" />
          <div className="flex-1">
            <p className="text-sm font-medium">
              Study is finished
            </p>
            <p className="text-sm text-muted-foreground">
              All participants submitted. Permanently locked.
            </p>
          </div>
        </div>
      )}
      {study.status === "active" && (
        <div className="flex items-center gap-3 rounded-md border border-warning/50 bg-warning/10 p-4">
          <Lock className="size-5 text-warning" />
          <div className="flex-1">
            <p className="text-sm font-medium">
              Active Study: Schema and dataset edits are frozen.
            </p>
            <p className="text-sm text-muted-foreground">
              To edit the questions or images,
              revert to draft — this will permanently delete existing participant submissions.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowRevertConfirm(true)}
            disabled={reopenStudy.isPending}
          >
            <LockOpen className="size-4" />
            Change to Draft
          </Button>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value} className="gap-1.5">
              <t.icon className="h-3.5 w-3.5" />
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="settings">
          <SettingsTab
            study={study}
            onDirtyChange={setSettingsDirty}
            saveRef={settingsSaveRef}
          />
        </TabsContent>

        <TabsContent value="schema">
          <SchemaTab
            study={study}
            onDirtyChange={setSchemaDirty}
            saveRef={schemaSaveRef}
          />
        </TabsContent>

        <TabsContent value="dataset">
          <DatasetTab study={study} onStudyChange={invalidateStudy} />
        </TabsContent>

        <TabsContent value="participants">
          <ParticipantsTab studyId={study.id} studyStatus={study.status} onStudyChange={invalidateStudy} />
        </TabsContent>

        <TabsContent value="evaluation">
          <EvaluationTab studyId={study.id} />
        </TabsContent>

        <TabsContent value="export">
          <ExportTab studyId={study.id} />
        </TabsContent>
      </Tabs>

      {/* Unsaved changes warning */}
      <AlertDialog open={!!pendingTab} onOpenChange={(open) => { if (!open) setPendingTab(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>You have unsaved changes in {TABS.find((t) => t.value === activeTab)?.label}</AlertDialogTitle>
            <AlertDialogDescription>
              Your changes will be lost if you navigate away without saving.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setPendingTab(null)}>
              <X className="h-3.5 w-3.5" />
              Cancel
            </AlertDialogCancel>
            <Button variant="outline" onClick={handleDiscardAndNavigate}>
              <Trash2 className="h-3.5 w-3.5" />
              Discard &amp; Continue
            </Button>
            <AlertDialogAction onClick={handleSaveAndNavigate}>
              <Save className="h-3.5 w-3.5" />
              Save &amp; Continue
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
