import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import DOMPurify from "dompurify";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Eye,
  Info,
  Keyboard,
  Loader2,
  RotateCcw,
  Send,
} from "lucide-react";
import { toast } from "sonner";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { User } from "@/types";
import { useAuth } from "@/hooks/use-auth";
import { useEvaluation } from "@/hooks/use-evaluation";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";
import { ImageSidebar } from "@/components/evaluation/image-sidebar";
import { ImagePanel } from "@/components/evaluation/image-panel";
import { RatingForm } from "@/components/evaluation/rating-form";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export default function EvaluatePage() {
  const { studyId: studyIdParam } = useParams<{ studyId: string }>();
  const studyId = Number(studyIdParam);
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const isImpersonating = !!user?.impersonating;
  const eval_ = useEvaluation(studyId, isImpersonating);

  const unimpersonateMutation = useMutation<User, Error>({
    mutationFn: () => api.post<User>("/api/admin/unimpersonate"),
    onSuccess: (admin) => {
      queryClient.setQueryData(["auth", "me"], admin);
      navigate(`/admin/studies/${studyId}`, { replace: true });
    },
    onError: () => {
      toast.error("Failed to stop impersonation");
    },
  });

  const handleBackToStudies = useCallback(async () => {
    try {
      await eval_.flushTimer();
      await eval_.flushPendingSaves();
      navigate("/studies");
    } catch {
      toast.error("Could not leave the evaluation because the latest rating has not been saved.");
    }
  }, [eval_, navigate]);

  // Invalidate studies list on unmount so completion counts are fresh
  useEffect(() => {
    return () => {
      void queryClient.invalidateQueries({ queryKey: ["studies"] });
    };
  }, [queryClient]);

  // Track isImpersonating in a ref so the unmount cleanup reads the latest value
  const isImpersonatingRef = useRef(isImpersonating);
  useEffect(() => {
    isImpersonatingRef.current = isImpersonating;
  }, [isImpersonating]);

  // Track mount state to distinguish React StrictMode double-invoke from real unmount
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // Auto-unimpersonate on hard navigation (address bar, browser reload).
  // sendBeacon is fire-and-forget and guaranteed to complete even during page unload.
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (isImpersonatingRef.current) {
        navigator.sendBeacon("/api/admin/unimpersonate", new Blob(['{}'], { type: 'application/json' }));
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);

  // Auto-unimpersonate on SPA navigation (React Router link/navigate).
  // setTimeout(0) ensures StrictMode's synchronous re-mount flips mountedRef back
  // to true before the callback runs, so we only fire on a real unmount.
  useEffect(() => {
    return () => {
      if (isImpersonatingRef.current) {
        setTimeout(() => {
          if (!mountedRef.current) {
            fetch("/api/admin/unimpersonate", {
              method: "POST",
              keepalive: true,
              credentials: "include",
            })
              .then((res) => { if (res.ok) return res.json(); })
              .then((admin) => {
                if (admin) queryClient.setQueryData(["auth", "me"], admin);
              })
              .catch(() => {});
          }
        }, 0);
      }
    };
  }, [queryClient]);

  // Redirect if the study is no longer active (reverted to draft while tab was open).
  // Only applies to actual participants — test users, impersonating admins, and admins
  // transitioning back after unimpersonation should never trigger this redirect.
  useEffect(() => {
    if (
      !eval_.studyLoading &&
      eval_.studyProject &&
      eval_.studyProject.status !== "active" &&
      eval_.studyProject.status !== "finished" &&
      user?.role === "participant" &&
      !user?.is_test_user &&
      !isImpersonating
    ) {
      toast.error("This study is no longer active.");
      navigate("/studies");
    }
  }, [eval_.studyLoading, eval_.studyProject, user, isImpersonating, navigate]);

  // ---- Modal states ----------------------------------------------------------
  const [instructionOpen, setInstructionOpen] = useState(false);
  const [confirmSubmitOpen, setConfirmSubmitOpen] = useState(false);
  const [confirmResetOpen, setConfirmResetOpen] = useState(false);

  // ---- Keyboard shortcuts ----------------------------------------------------
  const maxScore = useMemo(() => {
    const questions = eval_.studyProject?.rating_schema?.questions ?? [];
    const focused = questions[eval_.focusedQuestionIndex];
    if (focused?.type === "ordinal") {
      return focused.max ?? 5;
    }
    return 9;
  }, [eval_.studyProject?.rating_schema?.questions, eval_.focusedQuestionIndex]);

  const handleKeyScore = useCallback(
    (score: number) => {
      if (eval_.isReadOnly || eval_.saveStatus.isFlushing || !eval_.currentRatingId) return;
      const questions = eval_.studyProject?.rating_schema?.questions ?? [];
      const focused = questions[eval_.focusedQuestionIndex];
      if (focused?.type === "ordinal") {
        const min = focused.min ?? 1;
        const max = focused.max ?? 5;
        if (score >= min && score <= max) {
          eval_.saveResponse(focused.id, score);
          // Auto-advance to next question
          eval_.advanceFocus();
        }
      }
    },
    [eval_],
  );

  useKeyboardShortcuts({
    onPrev: () => void eval_.goPrev(),
    onNext: () => void eval_.goNext(),
    onScore: handleKeyScore,
    onAdvanceFocus: eval_.advanceFocus,
    enabled: true,
    maxScore,
  });

  // ---- Submit flow -----------------------------------------------------------
  const handleSubmitClick = useCallback(async () => {
    try {
      const status = await eval_.checkCompletion();
      if (status.complete) {
        setConfirmSubmitOpen(true);
      } else {
        toast.error("All images must be fully answered before submitting.");
      }
    } catch {
      toast.error("Failed to save latest ratings or check completion status.");
    }
  }, [eval_]);

  const handleConfirmSubmit = useCallback(async () => {
    try {
      await eval_.submit();
      toast.success("Evaluation submitted successfully.");
      setConfirmSubmitOpen(false);
    } catch {
      toast.error("Failed to save latest ratings or submit evaluation.");
    }
  }, [eval_]);

  // ---- Test user reset -------------------------------------------------------
  const resetMutation = useMutation({
    mutationFn: () => api.post("/api/auth/test-user-reset"),
    onSuccess: () => {
      toast.success("Test data reset. Reloading...");
      void queryClient.invalidateQueries();
      setTimeout(() => {
        window.location.reload();
      }, 500);
    },
    onError: () => {
      toast.error("Failed to reset test data.");
    },
  });

  // ---- Derived data ----------------------------------------------------------
  const schema = eval_.studyProject?.rating_schema ?? { questions: [] };
  const responses = eval_.currentRating?.responses ?? {};
  const uncertaintyValue = eval_.currentRating?.uncertainty ?? false;
  const uncertaintyEnabled = eval_.studyProject?.uncertainty_enabled ?? false;
  const sessionInstruction = eval_.studyProject?.session_instruction;
  const instructionStorageKey = studyIdParam ? `instruction_seen_${studyIdParam}` : null;
  const [dismissedInstructionKeys, setDismissedInstructionKeys] = useState<Record<string, true>>({});
  const instructionSeen =
    !instructionStorageKey ||
    Boolean(dismissedInstructionKeys[instructionStorageKey]) ||
    sessionStorage.getItem(instructionStorageKey) === "1";

  const instructionDialogOpen = instructionOpen || Boolean(sessionInstruction && !instructionSeen);

  const closeInstructionDialog = useCallback(() => {
    setInstructionOpen(false);
    if (instructionStorageKey) {
      setDismissedInstructionKeys((prev) => ({
        ...prev,
        [instructionStorageKey]: true,
      }));
      sessionStorage.setItem(instructionStorageKey, "1");
    }
  }, [instructionStorageKey]);

  const completionPct = useMemo(() => {
    const images = eval_.imageList;
    if (images.length === 0) return 0;
    const completed = images.filter((img) => img.status === "complete").length;
    return Math.round((completed / images.length) * 100);
  }, [eval_.imageList]);

  useEffect(() => {
    if (instructionDialogOpen || eval_.imageListLoading || eval_.imageList.length === 0) return;

    const sidebar = document.querySelector<HTMLElement>('[data-image-sidebar="true"]');
    const currentItem = document.querySelector<HTMLElement>(
      `[data-image-sidebar="true"] [data-image-position="${eval_.currentPosition}"]`,
    );

    if (!sidebar || !currentItem) return;

    const viewportTop = sidebar.scrollTop;
    const viewportBottom = viewportTop + sidebar.clientHeight;
    const itemTop = currentItem.offsetTop;
    const itemBottom = itemTop + currentItem.offsetHeight;

    if (itemTop >= viewportTop && itemBottom <= viewportBottom) return;

    const targetTop = Math.max(
      itemTop - sidebar.clientHeight / 2 + currentItem.offsetHeight / 2,
      0,
    );

    sidebar.scrollTop = targetTop;
  }, [
    eval_.currentPosition,
    eval_.currentImageData?.dataset_image_id,
    eval_.imageList.length,
    eval_.imageListLoading,
    instructionDialogOpen,
  ]);

  // ---- Loading state ---------------------------------------------------------
  if (eval_.studyLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-muted-foreground">Loading evaluation...</div>
      </div>
    );
  }

  if (!eval_.studyProject) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">Study not found.</p>
        <Button variant="outline" onClick={() => navigate("/studies")}>
          <ArrowLeft className="size-4" />
          Back to Studies
        </Button>
      </div>
    );
  }

  if (!eval_.imageListLoading && eval_.imageList.length === 0) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">
          No images in this study yet.
        </p>
        <Button variant="outline" onClick={() => navigate("/studies")}>
          <ArrowLeft className="size-4" />
          Back to Studies
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* -- Top bar: back + name + badge ----------------------------------- */}
      <header className="flex items-center gap-3 border-b border-border px-4 py-3">
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => void handleBackToStudies()} disabled={isImpersonating || eval_.saveStatus.isFlushing}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <Separator orientation="vertical" className="h-5" />
        <h1 className="text-sm font-semibold text-foreground">{eval_.studyProject.name}</h1>
        {eval_.isSubmitted && (
          <Badge className="bg-success text-success-foreground">Submitted</Badge>
        )}
      </header>

      {/* -- Read-only banner ----------------------------------------------- */}
      {eval_.isSubmitted && (
        <div className="bg-green-50 border-b border-green-200 px-4 py-2 text-center text-sm text-green-800 dark:bg-green-950/30 dark:border-green-800 dark:text-green-200">
          This evaluation has been submitted and is read-only.
        </div>
      )}

      {/* -- Three-panel layout --------------------------------------------- */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Image sidebar */}
        <ImageSidebar
          images={eval_.imageList}
          currentPosition={eval_.currentPosition}
          onSelect={(pos) => void eval_.goToImage(pos)}
          loading={eval_.imageListLoading}
        />

        {/* Center: Image panel + footer */}
        <div className="flex flex-1 flex-col min-w-0">
          {/* Image viewer */}
          <ImagePanel
            imageData={eval_.currentImageData}
            loading={eval_.imageDataLoading}
            viewerMode={eval_.studyProject.default_image_viewer}
            shortcutMode="evaluation"
          />

          {/* -- Impersonation banner --------------------------------------- */}
          {isImpersonating && (
            <div className="flex items-center justify-center gap-3 border-t border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
              <Eye className="size-4 shrink-0" />
              <span>
                Viewing as <strong>{user?.first_name} {user?.last_name}</strong>
              </span>
              <Button
                variant="outline"
                size="sm"
                className="h-6 text-xs"
                onClick={() => unimpersonateMutation.mutate()}
                disabled={unimpersonateMutation.isPending}
              >
                Back to Admin
              </Button>
            </div>
          )}

          {/* -- Bottom bar ------------------------------------------------- */}
          <footer className="flex items-center justify-between border-t border-border bg-card px-4 py-2.5">
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => void eval_.goPrev()}
                disabled={eval_.currentPosition <= 1 || eval_.saveStatus.isFlushing}
                title="Previous image (Left arrow)"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-xs text-muted-foreground">
                {eval_.currentPosition} / {eval_.imageList.length || "..."}
              </span>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => void eval_.goNext()}
                disabled={
                  eval_.saveStatus.isFlushing ||
                  eval_.currentPosition >=
                  (eval_.imageList.length || eval_.currentImageData?.total_images || 0)
                }
                title="Next image (Right arrow)"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex items-center gap-3">
              <Progress value={completionPct} className="h-1.5 w-48" />
              <span className="text-xs text-muted-foreground">{completionPct}%</span>
              {eval_.saveStatus.errorCount > 0 ? (
                <span className="flex items-center gap-1 text-xs text-destructive" title={eval_.saveStatus.lastError ?? undefined}>
                  <AlertTriangle className="size-3.5" />
                  Save failed
                </span>
              ) : eval_.saveStatus.pendingCount > 0 ? (
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" />
                  Saving
                </span>
              ) : null}
            </div>

            <div className="flex items-center gap-2">
              {/* Keyboard shortcuts */}
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" size="icon" className="h-8 w-8" title="Keyboard shortcuts">
                    <Keyboard className="h-4 w-4" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="end" side="top" className="w-64">
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold">Keyboard Shortcuts</h3>
                    <div className="space-y-2 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Previous image</span>
                        <kbd className="rounded border bg-muted px-1.5 py-0.5 text-xs font-mono">&larr;</kbd>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Next image</span>
                        <kbd className="rounded border bg-muted px-1.5 py-0.5 text-xs font-mono">&rarr;</kbd>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Set score</span>
                        <div className="flex gap-0.5">
                          <kbd className="rounded border bg-muted px-1.5 py-0.5 text-xs font-mono">0</kbd>
                          <span className="text-muted-foreground">-</span>
                          <kbd className="rounded border bg-muted px-1.5 py-0.5 text-xs font-mono">9</kbd>
                        </div>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Next question</span>
                        <kbd className="rounded border bg-muted px-1.5 py-0.5 text-xs font-mono">Tab</kbd>
                      </div>
                    </div>
                  </div>
                </PopoverContent>
              </Popover>

              {/* Session instruction button */}
              {sessionInstruction && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setInstructionOpen(true)}
                >
                  <Info className="size-4" />
                  Instructions
                </Button>
              )}

              {/* Test user reset */}
              {user?.is_test_user && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setConfirmResetOpen(true)}
                  disabled={resetMutation.isPending}
                >
                  <RotateCcw className="size-4" />
                  Reset
                </Button>
              )}

              {/* Submit button */}
              {!eval_.isSubmitted && (
                isImpersonating ? (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span tabIndex={0}>
                          <Button size="sm" disabled>
                            <Send className="size-4" />
                            Submit
                          </Button>
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        Cannot submit while viewing as another participant
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ) : completionPct < 100 ? (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span tabIndex={0}>
                          <Button size="sm" disabled>
                            <Send className="size-4" />
                            Submit
                          </Button>
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        All images must be fully answered before submitting
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ) : (
                  <Button
                    size="sm"
                    onClick={() => void handleSubmitClick()}
                    disabled={eval_.submitPending || eval_.saveStatus.isFlushing}
                  >
                    <Send className="size-4" />
                    Submit
                  </Button>
                )
              )}
            </div>
          </footer>
        </div>

        {/* Right: Rating form */}
        <RatingForm
          imageLabel={`Image ${eval_.currentPosition}`}
          questionAttributes={eval_.currentImageData?.question_attributes}
          valueScopeKey={eval_.currentImageData?.dataset_image_id ?? eval_.currentPosition}
          currentStatus={
            eval_.imageList.find((img) => img.position === eval_.currentPosition)?.status
          }
          schema={schema}
          responses={responses}
          uncertainty={uncertaintyValue}
          uncertaintyEnabled={uncertaintyEnabled}
          readOnly={eval_.isReadOnly || !eval_.currentRatingId || eval_.saveStatus.isFlushing}
          onSaveResponse={eval_.saveResponse}
          onSaveTextResponse={eval_.saveTextResponse}
          onSaveUncertainty={eval_.saveUncertainty}
          onSaveFailureReason={eval_.saveFailureReason}
          onFocusQuestion={eval_.setFocusedQuestionIndex}
          focusedQuestionIndex={eval_.focusedQuestionIndex}
        />
      </div>

      {/* -- Session Instruction Modal -------------------------------------- */}
      <Dialog
        open={instructionDialogOpen}
        onOpenChange={(open) => {
          if (open) {
            setInstructionOpen(true);
            return;
          }
          closeInstructionDialog();
        }}
      >
        <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader className="sr-only">
            <DialogTitle>Session Instructions</DialogTitle>
          </DialogHeader>
          {sessionInstruction && (
            <div
              className="prose prose-sm dark:prose-invert max-w-none leading-snug [&_p]:my-1 [&_h1]:my-2 [&_h2]:my-2 [&_h3]:my-1.5 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0"
              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(sessionInstruction) }}
            />
          )}
          <DialogFooter>
            <Button onClick={closeInstructionDialog}>
              Continue
              <ArrowRight className="size-4" />
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* -- Confirm Submit Dialog ------------------------------------------ */}
      <AlertDialog
        open={confirmSubmitOpen}
        onOpenChange={setConfirmSubmitOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Submit Evaluation?</AlertDialogTitle>
            <AlertDialogDescription>
              All images are complete. Once submitted, you will not be able to
              make further changes. Are you sure you want to submit?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void handleConfirmSubmit()}
              disabled={eval_.submitPending || eval_.saveStatus.pendingCount > 0}
            >
              Submit
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* -- Confirm Reset Dialog ------------------------------------------- */}
      <AlertDialog
        open={confirmResetOpen}
        onOpenChange={setConfirmResetOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Test Data?</AlertDialogTitle>
            <AlertDialogDescription>
              This will delete all your ratings and reset submission states
              across all studies. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                resetMutation.mutate();
                setConfirmResetOpen(false);
              }}
            >
              Reset All Data
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
