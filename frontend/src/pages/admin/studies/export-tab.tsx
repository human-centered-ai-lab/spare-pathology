import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Download, AlertTriangle, CheckCircle2, Info } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

interface ExportCheck {
  complete: boolean;
  warning: string | null;
  total_users: number;
  submitted_users: number;
}

interface ExportTabProps {
  studyId: number;
}

export function ExportTab({ studyId }: ExportTabProps) {
  const { data, isLoading } = useQuery<ExportCheck>({
    queryKey: ["admin", "studies", String(studyId), "export", "check"],
    queryFn: () =>
      api.get<ExportCheck>(
        `/api/admin/studies/${studyId}/export/check`,
      ),
  });

  function handleDownload() {
    // Open the CSV download URL in a new tab / trigger download
    const link = document.createElement("a");
    link.href = `/api/admin/studies/${studyId}/export`;
    link.download = `study-${studyId}-export.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const completionPct = data && data.total_users > 0
    ? (data.submitted_users / data.total_users) * 100
    : 0;
  const allSubmitted = data ? completionPct >= 100 : false;

  return (
    <div className="grid grid-cols-2 gap-4 items-stretch">
      {/* Export Data Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Download className="size-5" />
            Export Data
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button onClick={handleDownload}>
            <Download className="size-4" />
            Download CSV
          </Button>

          <div className="flex items-start gap-2 text-xs text-muted-foreground">
            <Info className="size-3.5 mt-0.5 shrink-0" />
            <span>Test users are excluded from export.</span>
          </div>
        </CardContent>
      </Card>

      {/* Completion Status Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            {allSubmitted ? (
              <CheckCircle2 className="size-5 text-success" />
            ) : (
              <AlertTriangle className="size-5 text-warning" />
            )}
            Completion Status
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {data ? (
            <>
              <div className="flex items-center justify-between text-sm">
                <span>
                  {data.submitted_users} of {data.total_users} users submitted
                </span>
                {!allSubmitted && (
                  <Badge
                    variant="outline"
                    className="text-warning border-warning/30"
                  >
                    Incomplete
                  </Badge>
                )}
                {allSubmitted && (
                  <Badge
                    variant="outline"
                    className="text-success border-success/30"
                  >
                    Complete
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-3">
                <Progress
                  value={completionPct}
                  className="h-2 flex-1"
                />
                <span className="text-sm font-medium tabular-nums">
                  {Math.round(completionPct)}%
                </span>
              </div>
            </>
          ) : (
            <p className="text-muted-foreground text-sm">
              Unable to load completion status.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
