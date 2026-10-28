import { Link } from "react-router-dom";
import { ArrowRight, Check, FileText, LayoutGrid } from "lucide-react";
import { useStudies, usePrefetchEvaluation } from "@/hooks/use-studies";
import type { ParticipantStudy } from "@/types";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max).trimEnd() + "...";
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function StudyCard({
  study,
  onPrefetch,
}: {
  study: ParticipantStudy;
  onPrefetch: (studyId: number, position?: number) => void;
}) {
  const { completion, submitted, submitted_at } = study;
  const progressLabel = `${completion.completed}/${completion.total} images rated`;

  const isStarted = completion.completed > 0;
  const actionLabel = submitted
    ? "Submitted"
    : isStarted
      ? "Continue Evaluation"
      : "Start Evaluation";

  return (
    <Card
      className="flex flex-col"
      onMouseEnter={() => !submitted && onPrefetch(study.id, study.last_viewed_position ?? 1)}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base">{study.name}</CardTitle>
          {submitted ? (
            <Badge variant="outline" className="border-success/30 bg-success/10 text-success">Submitted</Badge>
          ) : study.status === "active" ? (
            <Badge variant="outline" className="border-success/30 bg-success/10 text-success">{study.status}</Badge>
          ) : (
            <Badge variant="outline" className="border-muted-foreground/30 bg-muted text-muted-foreground">{study.status}</Badge>
          )}
        </div>
        {study.description && (
          <CardDescription>
            {truncate(study.description, 100)}
          </CardDescription>
        )}
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-4">
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{progressLabel}</span>
            <span>{completion.pct}%</span>
          </div>
          <Progress value={completion.pct} className="h-1.5" />
        </div>

        {submitted && submitted_at && (
          <p className="text-muted-foreground text-sm">
            Submitted on {formatDate(submitted_at)}
          </p>
        )}

        <div className="flex flex-wrap gap-2 mt-auto pt-2">
          {submitted ? (
            <Button disabled className="flex-1">
              <Check />
              Submitted
            </Button>
          ) : (
            <Button asChild className="flex-1">
              <Link to={`/studies/${study.id}/evaluate`}>
                {actionLabel}
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          )}

          {study.has_protocol_pdf && (
            <Button variant="outline" size="sm" asChild>
              <a
                href={`/api/studies/${study.id}/protocol-pdf`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <FileText />
                Study Protocol
              </a>
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function StudyCardSkeleton() {
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-5 w-20 rounded-full" />
        </div>
        <Skeleton className="h-4 w-full" />
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-8" />
          </div>
          <Skeleton className="h-1.5 w-full rounded-full" />
        </div>
        <Skeleton className="h-9 w-full" />
      </CardContent>
    </Card>
  );
}

export default function StudiesPage() {
  const { data: studies, isLoading, error } = useStudies();
  const prefetchEvaluation = usePrefetchEvaluation();

  return (
    <div className="space-y-4">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
          <LayoutGrid className="size-6" />
          <span>My Studies</span>
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">View your assigned studies and continue evaluations.</p>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
          Failed to load studies. Please try again later.
        </div>
      )}

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <StudyCardSkeleton key={i} />
          ))}
        </div>
      )}

      {studies && studies.length === 0 && (
        <div className="py-12 text-center">
          <p className="text-muted-foreground text-lg">
            You are not assigned to any studies yet.
          </p>
        </div>
      )}

      {studies && studies.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {studies.map((study) => (
            <StudyCard key={study.id} study={study} onPrefetch={prefetchEvaluation} />
          ))}
        </div>
      )}
    </div>
  );
}
