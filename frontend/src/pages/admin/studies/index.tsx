import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FolderKanban, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  useAdminStudies,
  useDeleteStudy,
  useCreateStudy,
} from "@/hooks/use-admin-studies";
import type { Study } from "@/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
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

export default function StudiesPage() {
  const { data: studies, isLoading } = useAdminStudies();
  const navigate = useNavigate();
  const deleteStudy = useDeleteStudy();
  const createStudy = useCreateStudy();

  const [deleteTarget, setDeleteTarget] = useState<Study | null>(null);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteStudy.mutateAsync({ studyId: deleteTarget.id });
      toast.success(`Study "${deleteTarget.name}" deleted.`);
      setDeleteTarget(null);
    } catch {
      toast.error("Failed to delete study.");
    }
  };

  const handleCreate = async () => {
    try {
      const study = await createStudy.mutateAsync({ name: "Untitled Study" });
      navigate(`/admin/studies/${study.id}/settings`);
    } catch {
      toast.error("Failed to create study.");
    }
  };

  return (
    <div className="p-4 space-y-4">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground"><FolderKanban className="size-6" />Studies</h1>
          <p className="mt-1 text-sm text-muted-foreground">Manage evaluation studies.</p>
        </div>
        <Button onClick={handleCreate} disabled={createStudy.isPending}>
          <Plus className="h-4 w-4" />
          New Study
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-36 w-full rounded-xl" />
          ))}
        </div>
      ) : !studies || studies.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          No studies found. Create your first study to get started.
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {studies.map((p) => (
            <Link key={p.id} to={`/admin/studies/${p.id}`}>
              <Card className="flex flex-col transition-all hover:border-primary/20 hover:shadow-sm h-full">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <CardTitle className="text-base">{p.name}</CardTitle>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className={cn(
                        "flex h-2 w-2 rounded-full",
                        p.status === "finished"
                          ? "bg-success"
                          : p.status === "active"
                            ? "bg-warning"
                            : "bg-muted-foreground/50"
                      )} />
                      <span className="text-sm font-medium capitalize">{p.status}</span>
                    </div>
                  </div>
                  <CardDescription>{p.description}</CardDescription>
                </CardHeader>
                <CardContent className="mt-auto space-y-2">
                  {(p.participant_count ?? 0) > 0 && (
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>Completion</span>
                        <span>{p.completed_count ?? 0}/{p.participant_count} submitted</span>
                      </div>
                      <Progress
                        value={((p.completed_count ?? 0) / (p.participant_count ?? 1)) * 100}
                        className="h-1.5"
                      />
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>{p.participant_count ?? 0} participants</span>
                      <span>{p.image_count ?? 0} images</span>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground hover:text-destructive"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setDeleteTarget(p);
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Study</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete{" "}
              <span className="font-medium">{deleteTarget?.name}</span>? This
              action cannot be undone. All associated data including ratings will
              be deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

    </div>
  );
}
