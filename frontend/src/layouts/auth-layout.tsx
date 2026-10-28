import type { ReactNode } from "react";

interface AuthLayoutProps {
  children: ReactNode;
}

export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="flex min-h-svh items-center justify-center bg-muted/40 p-4">
      {children}
    </div>
  );
}
