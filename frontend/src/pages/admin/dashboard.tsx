import { Link } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  Database,
  FolderKanban,
  ListChecks,
  Images,
  UserPlus,
  BarChart3,
  ArrowRight,
  Rocket,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const workflowSteps = [
  {
    number: 1,
    title: "Create Users",
    icon: Users,
    description:
      "Add accounts for study participants that will rate images.",
    link: "/admin/users/create",
    linkLabel: "Add User",
  },
  {
    number: 2,
    title: "Upload Datasets",
    icon: Database,
    description:
      "Upload your images that will be used for evaluation.",
    link: "/admin/images",
    linkLabel: "Upload a Dataset",
  },
  {
    number: 3,
    title: "Create a Study",
    icon: FolderKanban,
    description:
      "A study ties together a dataset, questions, and participants into a complete evaluation.",
    link: "/admin/studies/new",
    linkLabel: "Create Study",
  },
] as const;

const studySubSteps = [
  {
    title: "Define Questions",
    icon: ListChecks,
    description:
      "Set up the rating schema: ordinal scales, free text, conditional logic, and pass/fail rules.",
  },
  {
    title: "Select Images",
    icon: Images,
    description:
      "Choose a dataset and pick which images participants will evaluate.",
  },
  {
    title: "Assign Participants",
    icon: UserPlus,
    description:
      "Study participants will see the study on their dashboard once it is active.",
  },
  {
    title: "Activate",
    icon: Rocket,
    description:
      "Activate the study to open it for evaluation.",
  },
  {
    title: "Evaluate the Results",
    icon: BarChart3,
    description:
      "View automatically computed statistics and export results as CSV.",
  },
] as const;

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-muted">
          <LayoutDashboard className="size-5 text-muted-foreground" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Getting Started
          </h1>
          <p className="text-sm text-muted-foreground">
            Welcome to SPaRE — a platform for multi-center evaluation of
            synthetic histopathology images.
          </p>
        </div>
      </div>

      <div className="space-y-4">
        {workflowSteps.map((step) => (
          <Card key={step.number}>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-semibold">
                  {step.number}
                </div>
                <div className="flex items-center gap-2">
                  <step.icon className="size-5 text-muted-foreground" />
                  <CardTitle className="text-lg">{step.title}</CardTitle>
                </div>
              </div>
              <CardDescription className="ml-11">
                {step.description}
              </CardDescription>
            </CardHeader>
            <CardContent className="ml-11 space-y-4">
              {step.number !== 3 && (
                <Button variant="outline" size="sm" asChild>
                  <Link to={step.link}>
                    {step.linkLabel}
                    <ArrowRight className="ml-1.5 size-3.5" />
                  </Link>
                </Button>
              )}
              {step.number === 3 && (
                <>
                  <div className="space-y-3">
                    {studySubSteps.map((sub, i) => (
                      <div key={i} className="flex items-start gap-3">
                        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
                          3.{i + 1}
                        </div>
                        <div className="flex items-center gap-2 pt-1">
                          <sub.icon className="size-4 shrink-0 text-muted-foreground" />
                          <span className="text-sm">
                            <span className="font-medium">{sub.title}</span>
                            <span className="text-muted-foreground"> · {sub.description}</span>
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                  {/* Study Lifecycle */}
                  <p className="text-sm text-muted-foreground mt-2">
                    The lifecycle of a study evolves through 3 stages:
                  </p>
                  <div className="flex items-center gap-3">
                    <div className="flex flex-1 items-start gap-2.5 rounded-md border p-2.5">
                      <span className="mt-0.5 flex size-2.5 shrink-0 rounded-full bg-muted-foreground/50" />
                      <div className="min-w-0">
                        <p className="text-xs font-semibold">Draft</p>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          Fully editable. Configure questions, images, and participants.
                        </p>
                      </div>
                    </div>
                    <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" />
                    <div className="flex flex-1 items-start gap-2.5 rounded-md border p-2.5">
                      <span className="mt-0.5 flex size-2.5 shrink-0 rounded-full bg-warning" />
                      <div className="min-w-0">
                        <p className="text-xs font-semibold">Active</p>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          Visible to participants. Questions and images cannot be changed anymore.
                        </p>
                      </div>
                    </div>
                    <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" />
                    <div className="flex flex-1 items-start gap-2.5 rounded-md border p-2.5">
                      <span className="mt-0.5 flex size-2.5 shrink-0 rounded-full bg-success" />
                      <div className="min-w-0">
                        <p className="text-xs font-semibold">Finished</p>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          All participants submitted. Permanently locked.
                        </p>
                      </div>
                    </div>
                  </div>

                  <Button variant="outline" size="sm" asChild>
                    <Link to={step.link}>
                      {step.linkLabel}
                      <ArrowRight className="ml-1.5 size-3.5" />
                    </Link>
                  </Button>
                </>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
