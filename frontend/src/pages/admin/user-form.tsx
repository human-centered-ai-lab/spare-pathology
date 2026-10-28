import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowLeft, Loader2, UserPlus, Pencil, Save, X, Check } from "lucide-react";
import { toast } from "sonner";
import { useUser, useCreateUser, useUpdateUser } from "@/hooks/use-users";
import { useAdminStudies } from "@/hooks/use-admin-studies";
import type { Study } from "@/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const baseFields = z.object({
  first_name: z.string().min(1, "First name is required"),
  last_name: z.string().min(1, "Last name is required"),
  email: z.string().min(1, "Email is required").email("Invalid email format"),
  institution: z.string(),
  role: z.enum(["admin", "participant"]),
  password: z.string(),
  is_test_user: z.boolean(),
  comments: z.string(),
  study_ids: z.array(z.number()),
});

type UserFormValues = z.infer<typeof baseFields>;

const userFormSchema = baseFields.superRefine((data, ctx) => {
  if (data.role === "participant" && !data.institution?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "Institution is required for participants",
      path: ["institution"],
    });
  }
});

const createSchema = baseFields.superRefine((data, ctx) => {
  if (data.role === "participant" && !data.institution?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "Institution is required for participants",
      path: ["institution"],
    });
  }
  if (!data.password?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "Password is required",
      path: ["password"],
    });
  }
});

export default function UserFormPage() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const isEdit = !!userId;

  const { data: existingUser, isLoading: userLoading } = useUser(userId ?? "0");
  const { data: studies, isLoading: studiesLoading } = useAdminStudies();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser(userId ?? "0");

  const form = useForm<UserFormValues>({
    resolver: zodResolver(isEdit ? userFormSchema : createSchema),
    defaultValues: {
      first_name: "",
      last_name: "",
      email: "",
      institution: "",
      role: "participant",
      password: "",
      is_test_user: false,
      comments: "",
      study_ids: [],
    },
  });

  useEffect(() => {
    if (isEdit && existingUser) {
      form.reset({
        first_name: existingUser.first_name,
        last_name: existingUser.last_name,
        email: existingUser.email,
        institution: existingUser.institution ?? "",
        role: existingUser.role,
        password: "",
        is_test_user: existingUser.is_test_user,
        comments: existingUser.comments ?? "",
        study_ids: existingUser.studies.map((s) => s.study_id),
      });
    }
  }, [isEdit, existingUser, form]);

  const onSubmit = async (values: UserFormValues) => {
    try {
      const payload: Record<string, unknown> = {
        first_name: values.first_name,
        last_name: values.last_name,
        email: values.email,
        institution: values.institution || "",
        role: values.role,
        is_test_user: values.is_test_user,
        comments: values.comments || "",
        study_ids: values.study_ids,
      };

      if (values.password?.trim()) {
        payload.password = values.password;
      }

      if (isEdit) {
        await updateUser.mutateAsync(payload);
        toast.success("User updated successfully.");
      } else {
        await createUser.mutateAsync(payload);
        toast.success("User created successfully.");
      }

      navigate("/admin/users");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "An error occurred";
      toast.error(message);
    }
  };

  const isSubmitting = createUser.isPending || updateUser.isPending;
  const watchRole = useWatch({ control: form.control, name: "role" });

  if (isEdit && userLoading) {
    return (
      <div className="p-4 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-4 mb-6">
        <Button variant="ghost" size="icon" onClick={() => navigate("/admin/users")}>
          <ArrowLeft className="size-4" />
        </Button>
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
            {isEdit ? <Pencil className="size-6" /> : <UserPlus className="size-6" />}
            {isEdit ? "Edit User" : "Create User"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {isEdit
              ? `Editing ${existingUser?.first_name ?? ""} ${existingUser?.last_name ?? ""}`
              : "Add a new user to the system."}
          </p>
        </div>
      </div>

      <Form {...form}>
        <form noValidate onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">User Information</CardTitle>
              <CardDescription>Basic account details.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 items-start">
                <FormField
                  control={form.control}
                  name="first_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>First Name</FormLabel>
                      <FormControl>
                        <Input placeholder="John" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="last_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Last Name</FormLabel>
                      <FormControl>
                        <Input placeholder="Doe" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="grid grid-cols-2 gap-4 items-start">
                {watchRole === "participant" && (
                  <FormField
                    control={form.control}
                    name="institution"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Institution</FormLabel>
                        <FormControl>
                          <Input
                            placeholder="University Hospital"
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}
                <FormField
                  control={form.control}
                  name="email"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Email</FormLabel>
                      <FormControl>
                        <Input
                          type="email"
                          placeholder="john.doe@example.com"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="grid grid-cols-2 gap-4 items-start">
                <FormField
                  control={form.control}
                  name="role"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Role</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        value={field.value}
                        key={field.value}
                      >
                        <FormControl>
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder="Select a role" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="participant">Participant</SelectItem>
                          <SelectItem value="admin">Admin</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Password{isEdit && " (leave blank to keep current)"}
                      </FormLabel>
                      <FormControl>
                        <Input
                          type="password"
                          placeholder={isEdit ? "Unchanged" : "Enter password"}
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="is_test_user"
                render={({ field }) => (
                  <FormItem className="flex items-center gap-3">
                    <FormControl>
                      <Switch
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <div className="space-y-0.5">
                      <FormLabel>Test User</FormLabel>
                      <FormDescription>
                        Test users are auto-assigned to new studies and excluded
                        from statistics.
                      </FormDescription>
                    </div>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="comments"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Comments</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Optional notes about this user..."
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Study Assignments</CardTitle>
              <CardDescription>
                Assign studies here or through the participants settings of a study.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {studiesLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-6 w-full" />
                  ))}
                </div>
              ) : !studies || studies.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No studies available.
                </p>
              ) : (
                <FormField
                  control={form.control}
                  name="study_ids"
                  render={() => (
                    <FormItem>
                      <div className="flex flex-wrap gap-2">
                        {studies.map((study: Study) => (
                          <FormField
                            key={study.id}
                            control={form.control}
                            name="study_ids"
                            render={({ field }) => {
                              const selected = field.value.includes(study.id);
                              return (
                                <button
                                  type="button"
                                  onClick={() => {
                                    if (selected) {
                                      field.onChange(field.value.filter((id) => id !== study.id));
                                    } else {
                                      field.onChange([...field.value, study.id]);
                                    }
                                  }}
                                  className={cn(
                                    "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition-colors",
                                    selected
                                      ? "border-primary bg-primary/10 text-primary"
                                      : "border-border bg-background text-muted-foreground hover:bg-muted/50"
                                  )}
                                >
                                  {selected && <Check className="size-3.5" />}
                                  {study.name}
                                </button>
                              );
                            }}
                          />
                        ))}
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
            </CardContent>
          </Card>

          <div className="flex gap-3">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <Loader2 className="size-4 animate-spin" />
              ) : isEdit ? (
                <Save className="size-4" />
              ) : (
                <UserPlus className="size-4" />
              )}
              {isEdit ? "Save Changes" : "Create User"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate("/admin/users")}
            >
              <X className="size-4" />
              Cancel
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
