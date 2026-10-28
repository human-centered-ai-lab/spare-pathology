import { useState } from "react";
import type { FormEvent } from "react";
import { toast } from "sonner";
import { useAuth } from "@/hooks/use-auth";
import { api } from "@/api/client";
import { Shield, Lock, User, Mail, Building, BadgeCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

function DetailRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-3 py-2.5">
      <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm font-medium truncate">{value}</p>
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const { user } = useAuth();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changingPassword, setChangingPassword] = useState(false);
  const [resetting, setResetting] = useState(false);

  const handlePasswordChange = async (e: FormEvent) => {
    e.preventDefault();

    if (newPassword !== confirmPassword) {
      toast.error("New passwords do not match");
      return;
    }

    if (newPassword.length < 6) {
      toast.error("New password must be at least 6 characters");
      return;
    }

    setChangingPassword(true);
    try {
      await api.post("/api/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: newPassword,
      });
      toast.success("Password changed successfully");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to change password");
    } finally {
      setChangingPassword(false);
    }
  };

  const handleResetTestData = async () => {
    setResetting(true);
    try {
      await api.post("/api/auth/test-user-reset");
      toast.success("Test data has been reset");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to reset test data");
    } finally {
      setResetting(false);
    }
  };

  if (!user) return null;

  const initials =
    (user.first_name?.[0] ?? "") + (user.last_name?.[0] ?? "");

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      {/* Profile header card */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex items-center gap-5">
            <Avatar className="h-16 w-16 border-2 border-primary/20">
              <AvatarFallback className="bg-primary/10 text-primary text-xl font-semibold">
                {initials}
              </AvatarFallback>
            </Avatar>
            <div>
              <h2 className="text-lg font-semibold text-foreground">
                {user.first_name} {user.last_name}
              </h2>
              <p className="text-sm text-muted-foreground">{user.email}</p>
              <span className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                <Shield className="h-3 w-3" />
                {user.role}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 2-column grid */}
      <div className="grid grid-cols-2 gap-6 items-start">
        {/* Left: Account Details */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <User className="h-4 w-4" />
              Account Details
            </CardTitle>
          </CardHeader>
          <CardContent>
            <DetailRow icon={User} label="First Name" value={user.first_name} />
            <Separator />
            <DetailRow icon={User} label="Last Name" value={user.last_name} />
            <Separator />
            <DetailRow icon={Mail} label="Email" value={user.email} />
            <Separator />
            <DetailRow
              icon={Building}
              label="Institution"
              value={user.institution || "Not specified"}
            />
            <Separator />
            <DetailRow icon={BadgeCheck} label="Role" value={user.role} />
          </CardContent>
        </Card>

        {/* Right: Change Password */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Lock className="h-4 w-4" />
              Change Password
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handlePasswordChange} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="current-password" className="text-xs">
                  Current Password
                </Label>
                <Input
                  id="current-password"
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="new-password" className="text-xs">
                  New Password
                </Label>
                <Input
                  id="new-password"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="confirm-password" className="text-xs">
                  Confirm New Password
                </Label>
                <Input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                />
              </div>
              <Button type="submit" className="w-full" disabled={changingPassword}>
                {changingPassword ? "Changing..." : "Change Password"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>

      {/* Test User Actions */}
      {user.is_test_user && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Test User Actions</CardTitle>
          </CardHeader>
          <CardContent>
            <Separator className="mb-3" />
            <p className="mb-3 text-sm text-muted-foreground">
              This will clear all your ratings and reset your progress across
              all studies. This action cannot be undone.
            </p>
            <Button
              variant="destructive"
              onClick={handleResetTestData}
              disabled={resetting}
            >
              {resetting ? "Resetting..." : "Reset Test Data"}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
