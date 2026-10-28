import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
} from "react-router-dom";
import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { AuthContext, useAuth, useAuthProvider } from "@/hooks/use-auth";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider } from "@/components/theme-provider";
import { ErrorBoundary } from "@/components/error-boundary";

// Layouts
import AuthLayout from "@/layouts/auth-layout";
import AdminLayout from "@/layouts/admin-layout";
import ParticipantLayout from "@/layouts/participant-layout";

// Pages (lazy-loaded for route-based code splitting)
const LoginPage = lazy(() => import("@/pages/auth/login"));
const ProfilePage = lazy(() => import("@/pages/auth/profile"));
const UsersPage = lazy(() => import("@/pages/admin/users"));
const UserFormPage = lazy(() => import("@/pages/admin/user-form"));
const AdminStudiesPage = lazy(() => import("@/pages/admin/studies"));
const StudyPage = lazy(() => import("@/pages/admin/studies/study"));
const ImagesPage = lazy(() => import("@/pages/admin/images"));
const AdminDatasetViewerPage = lazy(() => import("@/pages/admin/dataset-viewer"));
const DashboardPage = lazy(() => import("@/pages/admin/dashboard"));
const StudiesPage = lazy(() => import("@/pages/participant/studies"));
const EvaluatePage = lazy(() => import("@/pages/participant/evaluate"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,
      retry: 1,
    },
  },
});

function AuthProvider({ children }: { children: ReactNode }) {
  const auth = useAuthProvider();
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

function AuthGate() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

function AdminGate() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  // If the admin landed here while impersonating (e.g. typed a URL while in
  // participant-view mode), call unimpersonate and wait before rendering.
  useEffect(() => {
    if (!user?.impersonating) return;
    void fetch("/api/admin/unimpersonate", { method: "POST", credentials: "include" })
      .then((res) => (res.ok ? res.json() : null))
      .then((admin) => { if (admin) queryClient.setQueryData(["auth", "me"], admin); })
      .catch(() => {});
  }, [user?.impersonating, queryClient]);

  if (user?.impersonating) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (user?.role !== "admin") {
    return <Navigate to="/studies" replace />;
  }

  return <Outlet />;
}

function ParticipantGate() {
  const { user } = useAuth();

  if (user?.role !== "participant") {
    return <Navigate to="/admin" replace />;
  }

  return <Outlet />;
}

export default function App() {
  return (
    <ThemeProvider>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TooltipProvider>
          <ErrorBoundary>
          <BrowserRouter>
            <Suspense fallback={<div className="flex min-h-svh items-center justify-center"><div className="text-muted-foreground">Loading...</div></div>}>
            <Routes>
              {/* Public route */}
              <Route
                path="/login"
                element={
                  <AuthLayout>
                    <LoginPage />
                  </AuthLayout>
                }
              />

              {/* Admin routes */}
              <Route element={<AuthGate />}>
                <Route element={<AdminGate />}>
                  <Route
                    path="/admin/images/:datasetName"
                    element={<AdminDatasetViewerPage />}
                  />
                  <Route path="/admin" element={<AdminLayout />}>
                    <Route index element={<DashboardPage />} />
                    <Route path="users" element={<UsersPage />} />
                    <Route path="users/create" element={<UserFormPage />} />
                    <Route
                      path="users/:userId/edit"
                      element={<UserFormPage />}
                    />
                    <Route path="studies" element={<AdminStudiesPage />} />
                    <Route
                      path="studies/:studyId"
                      element={<StudyPage />}
                    />
                    <Route
                      path="studies/:studyId/:tab"
                      element={<StudyPage />}
                    />
                    <Route path="images" element={<ImagesPage />} />
                    <Route path="profile" element={<ProfilePage />} />
                  </Route>
                </Route>
              </Route>

              {/* Participant routes */}
              <Route element={<AuthGate />}>
                <Route element={<ParticipantGate />}>
                  <Route path="/" element={<ParticipantLayout />}>
                    <Route
                      index
                      element={<Navigate to="studies" replace />}
                    />
                    <Route path="studies" element={<StudiesPage />} />
                    <Route path="profile" element={<ProfilePage />} />
                  </Route>
                </Route>
              </Route>

              {/* Full-screen evaluate route (no layout) */}
              <Route element={<AuthGate />}>
                <Route
                  path="/studies/:studyId/evaluate"
                  element={<EvaluatePage />}
                />
              </Route>

              {/* Catch-all */}
              <Route path="*" element={<Navigate to="/login" replace />} />
            </Routes>
            </Suspense>
          </BrowserRouter>
          </ErrorBoundary>
          <Toaster />
        </TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>
    </ThemeProvider>
  );
}
