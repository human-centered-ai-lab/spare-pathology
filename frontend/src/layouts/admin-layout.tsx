import { Fragment } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Collapsible } from "radix-ui";
import {
  Users,
  Database,
  FolderKanban,
  Plus,
  ChevronRight,
  LogOut,
  User,
  Settings,
  ListChecks,
  Images,
  BarChart3,
  Download,
  UserPlus,
  Pencil,
  LayoutDashboard,
  type LucideIcon,
} from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { useAdminStudies } from "@/hooks/use-admin-studies";
import { useUsers } from "@/hooks/use-users";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarProvider,
} from "@/components/ui/sidebar";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

function StatusDot({ status }: { status: string }) {
  const colorClass =
    status === "finished"
      ? "bg-success"
      : status === "active"
        ? "bg-warning"
        : "bg-muted-foreground/50";

  return <span className={`inline-block size-2 rounded-full ${colorClass}`} />;
}

const segmentMeta: Record<string, { label: string; icon?: LucideIcon }> = {
  admin: { label: "Admin", icon: LayoutDashboard },
  users: { label: "Users", icon: Users },
  studies: { label: "Studies", icon: FolderKanban },
  images: { label: "Datasets", icon: Database },
  profile: { label: "Profile", icon: User },
  create: { label: "Create", icon: UserPlus },
  edit: { label: "Edit", icon: Pencil },
  settings: { label: "Settings", icon: Settings },
  schema: { label: "Questions", icon: ListChecks },
  dataset: { label: "Images", icon: Images },
  participants: { label: "Participants", icon: Users },
  evaluation: { label: "Evaluation", icon: BarChart3 },
  export: { label: "Export", icon: Download },
};

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const { data: studies, isLoading: studiesLoading } = useAdminStudies();
  const { data: users } = useUsers();
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const initials = user
    ? `${user.first_name?.[0] ?? ""}${user.last_name?.[0] ?? ""}`
    : "";

  // Study tab segments — shown as tabs inside the study page, not in breadcrumbs
  const studyTabs = new Set(["settings", "schema", "dataset", "participants", "evaluation", "export"]);

  // Build breadcrumbs from pathname
  const pathSegments = location.pathname.split("/").filter(Boolean);
  const crumbs = pathSegments
    .map((segment, index) => {
      let path = "/" + pathSegments.slice(0, index + 1).join("/");

      const meta = segmentMeta[segment];
      let label = meta?.label ?? segment;
      let Icon = meta?.icon;

      // Resolve numeric IDs to names
      if (/^\d+$/.test(segment)) {
        const parentSegment = pathSegments[index - 1];
        if (parentSegment === "studies" && studies) {
          const study = studies.find((s) => String(s.id) === segment);
          if (study) label = study.name;
          Icon = Pencil;
        } else if (parentSegment === "users" && users) {
          const u = users.find((u) => String(u.id) === segment);
          if (u) {
            label = `${u.first_name} ${u.last_name}`.trim() || u.email;
            Icon = User;
          }
          path = "/admin/users";
        }
      }

      // Skip study tab segments from breadcrumbs
      const parentSegment = pathSegments[index - 1];
      if (parentSegment && /^\d+$/.test(parentSegment) && studyTabs.has(segment)) {
        return null;
      }

      return { path, label, Icon };
    })
    .filter((c) => c !== null)
    .map((c, _i, arr) => ({ ...c, isLast: c === arr[arr.length - 1] }));

  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" asChild>
                <Link to="/admin">
                  <img src="/favicon.svg" alt="" className="size-8 shrink-0" />
                  <div className="flex flex-col gap-0.5 leading-none">
                    <span className="font-semibold">SPaRE</span>
                    <span className="text-xs text-muted-foreground">
                      Admin
                    </span>
                  </div>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>

        <div className="mx-4 border-t border-sidebar-border" />

        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Navigation</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    isActive={location.pathname === "/admin"}
                  >
                    <Link to="/admin">
                      <LayoutDashboard className="size-4" />
                      <span>Getting Started</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    isActive={location.pathname.startsWith("/admin/users")}
                  >
                    <Link to="/admin/users">
                      <Users className="size-4" />
                      <span>Users</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    isActive={location.pathname === "/admin/images"}
                  >
                    <Link to="/admin/images">
                      <Database className="size-4" />
                      <span>Datasets</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <Collapsible.Root
                  asChild
                  defaultOpen
                  className="group/collapsible"
                >
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      asChild
                      isActive={location.pathname === "/admin/studies"}
                    >
                      <Link to="/admin/studies">
                        <FolderKanban className="size-4" />
                        <span>Studies</span>
                      </Link>
                    </SidebarMenuButton>
                    <Collapsible.Trigger asChild>
                      <SidebarMenuAction className="data-[state=open]:rotate-90 transition-transform">
                        <ChevronRight className="size-4" />
                      </SidebarMenuAction>
                    </Collapsible.Trigger>
                    <Collapsible.Content className="overflow-hidden data-[state=open]:animate-collapsible-down data-[state=closed]:animate-collapsible-up">
                      <SidebarMenuSub>
                        {studiesLoading ? (
                          <>
                            <SidebarMenuSubItem>
                              <div className="px-2 py-1">
                                <Skeleton className="h-3.5 w-full" />
                              </div>
                            </SidebarMenuSubItem>
                            <SidebarMenuSubItem>
                              <div className="px-2 py-1">
                                <Skeleton className="h-3.5 w-3/4" />
                              </div>
                            </SidebarMenuSubItem>
                          </>
                        ) : (
                          studies?.map((study) => (
                            <SidebarMenuSubItem key={study.id}>
                              <SidebarMenuSubButton
                                asChild
                                size="sm"
                                isActive={location.pathname.startsWith(
                                  `/admin/studies/${study.id}`
                                )}
                              >
                                <Link to={`/admin/studies/${study.id}`}>
                                  <StatusDot status={study.status} />
                                  <span>{study.name}</span>
                                </Link>
                              </SidebarMenuSubButton>
                            </SidebarMenuSubItem>
                          ))
                        )}
                        {!studiesLoading && studies && studies.length === 0 && (
                          <SidebarMenuSubItem>
                            <div className="px-2 py-1 text-xs text-muted-foreground">
                              No studies yet
                            </div>
                          </SidebarMenuSubItem>
                        )}
                        <SidebarMenuSubItem>
                          <SidebarMenuSubButton asChild size="sm">
                            <Link to="/admin/studies/new" className="text-muted-foreground">
                              <Plus className="size-3" />
                              <span>New Study</span>
                            </Link>
                          </SidebarMenuSubButton>
                        </SidebarMenuSubItem>
                      </SidebarMenuSub>
                    </Collapsible.Content>
                  </SidebarMenuItem>
                </Collapsible.Root>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>

        <SidebarFooter>
          <div className="border-t border-sidebar-border mx-4" />
          <div className="flex items-center gap-3 px-4 py-2">
            <Avatar size="sm">
              <AvatarFallback>{initials}</AvatarFallback>
            </Avatar>
            <div className="flex flex-1 flex-col text-left text-sm leading-tight min-w-0">
              <span className="truncate font-medium">
                {user?.first_name} {user?.last_name}
              </span>
              <span className="truncate text-xs text-muted-foreground">
                {user?.email}
              </span>
            </div>
          </div>
          <div className="ml-7 translate-x-px border-l border-sidebar-border pl-2.5 py-0.5">
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive={location.pathname === "/admin/profile"} size="sm">
                  <Link to="/admin/profile">
                    <User className="size-3.5" />
                    <span>Profile</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton onClick={handleLogout} size="sm">
                  <LogOut className="size-3.5" />
                  <span>Log out</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </div>
        </SidebarFooter>
      </Sidebar>

      <SidebarInset>
        <header className="flex items-center gap-3 border-b border-border px-4" style={{ height: 48 }}>
          <Breadcrumb>
            <BreadcrumbList>
              {crumbs.map((crumb, i) => (
                <Fragment key={crumb.path}>
                  {i > 0 && <BreadcrumbSeparator />}
                  <BreadcrumbItem>
                    {crumb.isLast ? (
                      <BreadcrumbPage className="flex items-center gap-1.5">
                        {crumb.Icon && <crumb.Icon className="size-3.5" />}
                        {crumb.label}
                      </BreadcrumbPage>
                    ) : (
                      <BreadcrumbLink asChild>
                        <Link to={crumb.path} className="flex items-center gap-1.5">
                          {crumb.Icon && <crumb.Icon className="size-3.5" />}
                          {crumb.label}
                        </Link>
                      </BreadcrumbLink>
                    )}
                  </BreadcrumbItem>
                </Fragment>
              ))}
            </BreadcrumbList>
          </Breadcrumb>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl px-8 py-8">
            <Outlet />
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
