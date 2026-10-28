import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { Study } from "@/types";
import { api } from "@/api/client";
import { DualPanelBuilder } from "@/components/dataset-builder/dual-panel-builder";
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

interface DatasetTabProps {
  study: Study;
  onStudyChange?: () => void;
}

interface DatasetListItem {
  name: string;
  image_count: number;
  attribute_names: string[];
}

export default function DatasetTab({ study, onStudyChange }: DatasetTabProps) {
  const studyId = study.id;
  const queryClient = useQueryClient();
  const isEditable = study.status === 'draft';
  const datasetName = study.dataset_name ?? null;

  const [pendingDataset, setPendingDataset] = useState<string | null>(null);
  const showConfirm = pendingDataset !== null;

  const imageCount = study.image_count ?? 0;
  const ratingCount = study.rating_count ?? 0;

  const datasetsQuery = useQuery<DatasetListItem[]>({
    queryKey: ["admin", "datasets"],
    queryFn: () => api.get<DatasetListItem[]>("/api/admin/datasets"),
  });

  const setDatasetMutation = useMutation({
    mutationFn: (name: string | null) =>
      api.put<Study>(`/api/admin/studies/${studyId}/settings`, {
        dataset_name: name ?? "",
      }),
    onSuccess: (updatedStudy) => {
      queryClient.setQueryData(
        ["admin", "studies", String(studyId)],
        updatedStudy,
      );
      queryClient.invalidateQueries({
        queryKey: ["admin", "studies", String(studyId), "dataset"],
      });
      queryClient.invalidateQueries({
        queryKey: ["admin", "datasets"],
      });
      toast.success("Dataset updated.");
      onStudyChange?.();
    },
    onError: () => {
      toast.error("Failed to update dataset.");
    },
  });

  function handleDatasetChange(val: string) {
    const newName = val || null;
    if (imageCount > 0 && newName !== datasetName) {
      setPendingDataset(newName);
    } else {
      setDatasetMutation.mutate(newName);
    }
  }

  function handleConfirmSwitch() {
    setDatasetMutation.mutate(pendingDataset);
    setPendingDataset(null);
  }

  function handleCancelSwitch() {
    setPendingDataset(null);
  }

  return (
    <div className="space-y-4">
      <DualPanelBuilder
        studyId={studyId}
        datasetName={datasetName}
        datasets={(datasetsQuery.data ?? []).map((ds) => ({ name: ds.name, image_count: ds.image_count }))}
        onDatasetChange={handleDatasetChange}
        datasetDisabled={!isEditable || setDatasetMutation.isPending}
        disabled={!isEditable}
        onChanged={onStudyChange}
      />

      {/* Confirmation dialog for switching datasets */}
      <AlertDialog open={showConfirm} onOpenChange={(open) => { if (!open) handleCancelSwitch(); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Switch dataset?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>
                  This study currently has <span className="font-semibold">{imageCount} image{imageCount !== 1 ? "s" : ""}</span> assigned
                  {ratingCount > 0 && (
                    <> and <span className="font-semibold">{ratingCount} rating{ratingCount !== 1 ? "s" : ""}</span></>
                  )}.
                </p>
                <p>
                  Switching to a different dataset will <span className="font-semibold">permanently remove</span> all
                  currently assigned images{ratingCount > 0 ? " and all associated ratings" : ""} from
                  this study.
                </p>
                <p className="text-destructive font-medium">
                  This action cannot be undone.
                </p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={handleConfirmSwitch}
            >
              Switch & Remove Images
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
