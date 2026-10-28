import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { ParticipantStatus, User } from "@/types";
import { toast } from "sonner";
import { UserPlus, Eye, UserMinus, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface AvailableUser {
  user_id: number;
  first_name: string;
  last_name: string;
  email: string;
  institution: string | null;
}

interface ParticipantsResponse {
  assigned: ParticipantStatus[];
  available: AvailableUser[];
}

interface ParticipantsTabProps {
  studyId: number;
  studyStatus: string;
  onStudyChange?: () => void;
}

export function ParticipantsTab({ studyId, studyStatus, onStudyChange }: ParticipantsTabProps) {
  const queryClient = useQueryClient();
  const [unassignTarget, setUnassignTarget] = useState<ParticipantStatus | null>(null);
  const [reactivateTarget, setReactivateTarget] = useState<AvailableUser | null>(null);

  const { data, isLoading } = useQuery<ParticipantsResponse>({
    queryKey: ["admin", "studies", String(studyId), "participants"],
    queryFn: () =>
      api.get<ParticipantsResponse>(
        `/api/admin/studies/${studyId}/participants`,
      ),
  });

  const invalidateParticipants = () => {
    queryClient.invalidateQueries({
      queryKey: ["admin", "studies", String(studyId), "participants"],
    });
  };

  const assignMutation = useMutation<
    { reactivated?: boolean },
    Error,
    { user_id: number; reactivate?: boolean }
  >({
    mutationFn: (body) =>
      api.post(`/api/admin/studies/${studyId}/participants/assign`, body),
    onSuccess: (data) => {
      if (data.reactivated) {
        toast.success("User assigned — study reactivated");
        onStudyChange?.();
      } else {
        toast.success("User assigned successfully");
        onStudyChange?.();
      }
      invalidateParticipants();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to assign user");
    },
  });

  const unassignMutation = useMutation<
    void,
    Error,
    { user_id: number; confirm: boolean }
  >({
    mutationFn: (body) =>
      api.post(`/api/admin/studies/${studyId}/participants/unassign`, body),
    onSuccess: () => {
      toast.success("User unassigned successfully");
      setUnassignTarget(null);
      invalidateParticipants();
      onStudyChange?.();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to unassign user");
    },
  });

  const impersonateMutation = useMutation<User, Error, number>({
    mutationFn: (userId) =>
      api.post<User>(`/api/admin/impersonate/${userId}`),
    onSuccess: () => {
      // Hard navigate — changing auth context (admin → participant) would
      // trigger AdminGate redirect before React router navigate can complete.
      window.location.href = `/studies/${studyId}/evaluate`;
    },
    onError: (err) => {
      toast.error(err.message || "Failed to impersonate user");
    },
  });

  function handleUnassign(participant: ParticipantStatus) {
    if (participant.status_key !== "not_started") {
      setUnassignTarget(participant);
    } else {
      unassignMutation.mutate({
        user_id: participant.user_id,
        confirm: true,
      });
    }
  }

  function confirmUnassign() {
    if (!unassignTarget) return;
    unassignMutation.mutate({
      user_id: unassignTarget.user_id,
      confirm: true,
    });
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const participants = data?.assigned ?? [];
  const availableUsers = data?.available ?? [];

  return (
    <div className="space-y-4">
      {/* Assign User Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <UserPlus className="size-4" />
            Assign User
          </CardTitle>
        </CardHeader>
        <CardContent>
          {availableUsers.length === 0 ? (
            <p className="text-muted-foreground text-xs py-4 text-center">
              All users are already assigned to this study.
            </p>
          ) : (
            <div className="space-y-1">
              {availableUsers.map((u) => (
                <div
                  key={u.user_id}
                  className="flex items-center justify-between rounded-md px-3 py-2 hover:bg-muted/50"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">
                      {u.first_name} {u.last_name}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {[u.email, u.institution].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="ml-3 shrink-0"
                    onClick={() => {
                      if (studyStatus === "finished") {
                        setReactivateTarget(u);
                      } else {
                        assignMutation.mutate({ user_id: u.user_id });
                      }
                    }}
                    disabled={assignMutation.isPending}
                  >
                    <UserPlus className="size-3.5" />
                    Assign
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Participants Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5 text-base">
            <Users className="size-4" />
            Study Participants
            <Badge variant="secondary" className="ml-2">
              {participants.length}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {participants.length === 0 ? (
            <p className="text-muted-foreground text-xs py-4 text-center">
              No participants assigned yet.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Institution</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Completion</TableHead>
                  <TableHead>Submitted At</TableHead>
                  <TableHead className="text-center">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {participants.map((p) => (
                  <TableRow key={p.user_id}>
                    <TableCell className="font-medium">
                      {p.first_name} {p.last_name}
                      {p.is_test_user && (
                        <Badge variant="outline" className="ml-2 text-xs">
                          Test
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>{p.institution ?? "-"}</TableCell>
                    <TableCell>
                      <StatusBadge statusKey={p.status_key} label={p.status_label} />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2 min-w-[120px]">
                        <Progress value={p.completion_pct} className="h-2 flex-1" />
                        <span className="text-xs text-muted-foreground w-[40px] text-right">
                          {Math.round(p.completion_pct)}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {p.submitted_at
                        ? new Date(p.submitted_at).toLocaleDateString()
                        : "-"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 text-xs gap-1"
                                onClick={() => impersonateMutation.mutate(p.user_id)}
                                disabled={impersonateMutation.isPending}
                              >
                                <Eye className="size-3.5" />
                                View
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-[220px] text-center">
                              Opens the evaluation as this participant sees it — browse their image ratings and progress. All scoring and submit actions are disabled.
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs gap-1 text-destructive hover:text-destructive"
                          onClick={() => handleUnassign(p)}
                          disabled={unassignMutation.isPending}
                          title="Unassign from study"
                        >
                          <UserMinus className="size-3.5" />
                          Unassign
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Unassign Confirmation Dialog */}
      <AlertDialog
        open={!!unassignTarget}
        onOpenChange={(open) => {
          if (!open) setUnassignTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Unassign Participant</AlertDialogTitle>
            <AlertDialogDescription>
              {unassignTarget?.first_name} {unassignTarget?.last_name} has existing ratings for this study.
              Unassigning will remove all their ratings. This action cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={confirmUnassign}
              disabled={unassignMutation.isPending}
            >
              {unassignMutation.isPending ? "Unassigning..." : "Unassign"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reactivate Confirmation Dialog */}
      <AlertDialog
        open={!!reactivateTarget}
        onOpenChange={(open) => {
          if (!open) setReactivateTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reactivate Study?</AlertDialogTitle>
            <AlertDialogDescription>
              This study is finished. Assigning {reactivateTarget?.first_name} {reactivateTarget?.last_name} will
              revert it to active so the new participant can evaluate.
              Existing submissions from other participants are preserved.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (reactivateTarget) {
                  assignMutation.mutate({
                    user_id: reactivateTarget.user_id,
                    reactivate: true,
                  });
                }
                setReactivateTarget(null);
              }}
              disabled={assignMutation.isPending}
            >
              Assign &amp; Reactivate
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function StatusBadge({
  statusKey,
  label,
}: {
  statusKey: ParticipantStatus["status_key"];
  label: string;
}) {
  if (statusKey === "submitted") {
    return (
      <Badge variant="outline" className="bg-success/10 text-success border-success/30">
        {label}
      </Badge>
    );
  }
  if (statusKey === "in_progress") {
    return (
      <Badge variant="outline" className="bg-warning/10 text-warning border-warning/30">
        {label}
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="text-muted-foreground">
      {label}
    </Badge>
  );
}
