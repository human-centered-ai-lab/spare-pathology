import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Study } from "@/types";

export function useAdminStudies() {
  return useQuery<Study[]>({
    queryKey: ["admin", "studies"],
    queryFn: () => api.get<Study[]>("/api/admin/studies"),
  });
}

export function useAdminStudy(id: number | string) {
  return useQuery<Study>({
    queryKey: ["admin", "studies", String(id)],
    queryFn: () => api.get<Study>(`/api/admin/studies/${id}`),
    enabled: !!id,
  });
}

export function useDeleteStudy() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, { studyId: number }>({
    mutationFn: ({ studyId }) =>
      api.delete<void>(`/api/admin/studies/${studyId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "studies"] });
    },
  });
}

export function useCreateStudy() {
  const queryClient = useQueryClient();

  return useMutation<Study, Error, { name: string; description?: string }>({
    mutationFn: (data) => api.post<Study>("/api/admin/studies", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "studies"] });
    },
  });
}
