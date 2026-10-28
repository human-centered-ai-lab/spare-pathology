import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api } from "@/api/client";
import type { ParticipantStudy, ImageListItem, ImageData } from "@/types";

export function useStudies() {
  return useQuery<ParticipantStudy[]>({
    queryKey: ["studies"],
    queryFn: () => api.get<ParticipantStudy[]>("/api/studies"),
  });
}

/** Prefetch image list + current image for a study without mutating resume state. */
export function usePrefetchEvaluation() {
  const queryClient = useQueryClient();

  return useCallback(
    (studyId: number, position = 1) => {
      void queryClient.prefetchQuery({
        queryKey: ["studies", studyId, "images"],
        queryFn: () =>
          api.get<ImageListItem[]>(`/api/studies/${studyId}/images`),
        staleTime: 30_000,
      });
      void queryClient.prefetchQuery({
        queryKey: ["studies", studyId, "image", position],
        queryFn: () =>
          api.get<ImageData>(`/api/studies/${studyId}/image/${position}?track=0`),
        staleTime: 30_000,
      });
    },
    [queryClient],
  );
}
