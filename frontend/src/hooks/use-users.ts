import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { User } from "@/types";

export interface UserDetail extends User {
  studies: {
    study_id: number;
    study_name: string;
    submitted: boolean;
    submitted_at: string | null;
    has_ratings: boolean;
  }[];
}

export function useUsers() {
  return useQuery<User[]>({
    queryKey: ["admin", "users"],
    queryFn: () => api.get<User[]>("/api/admin/users"),
  });
}

export function useUser(id: number | string) {
  return useQuery<UserDetail>({
    queryKey: ["admin", "users", String(id)],
    queryFn: () => api.get<UserDetail>(`/api/admin/users/${id}`),
    enabled: !!id,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();

  return useMutation<UserDetail, Error, Record<string, unknown>>({
    mutationFn: (data) => api.post<UserDetail>("/api/admin/users", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

export function useUpdateUser(id: number | string) {
  const queryClient = useQueryClient();

  return useMutation<UserDetail, Error, Record<string, unknown>>({
    mutationFn: (data) => api.put<UserDetail>(`/api/admin/users/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "users", String(id)] });
    },
  });
}

export function useDeleteUser() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, { userId: number; confirm?: boolean }>({
    mutationFn: ({ userId, confirm }) => {
      const qs = confirm ? "?confirm=yes" : "";
      return api.delete<void>(`/api/admin/users/${userId}${qs}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

export function useResetPassword() {
  return useMutation<{ message: string }, Error, { userId: number; newPassword: string }>({
    mutationFn: ({ userId, newPassword }) =>
      api.post<{ message: string }>(`/api/admin/users/${userId}/reset-password`, {
        new_password: newPassword,
      }),
  });
}
