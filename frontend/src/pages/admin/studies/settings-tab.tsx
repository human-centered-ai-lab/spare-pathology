import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Loader2,
  Upload,
  Download,
  Trash2,
  Save,
  Pencil,
} from "lucide-react";
import { api } from "@/api/client";
import type { Study } from "@/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RichTextEditor } from "@/components/ui/rich-text-editor";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

interface SettingsTabProps {
  study: Study;
  onDirtyChange?: (dirty: boolean) => void;
  saveRef?: React.MutableRefObject<(() => Promise<void>) | null>;
}

export default function SettingsTab({ study, onDirtyChange, saveRef }: SettingsTabProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Settings form state
  const [description, setDescription] = useState(study.description ?? "");
  const [sessionInstruction, setSessionInstruction] = useState(
    study.session_instruction ?? ""
  );
  const [defaultImageViewer, setDefaultImageViewer] = useState<
    "native" | "xopat"
  >(study.default_image_viewer ?? "native");

  // Sync from study prop when it updates (state-based tracking)
  const [prevStudyId, setPrevStudyId] = useState(study.id);
  if (prevStudyId !== study.id) {
    setPrevStudyId(study.id);
    setDescription(study.description ?? "");
    setSessionInstruction(study.session_instruction ?? "");
    setDefaultImageViewer(study.default_image_viewer ?? "native");
  }

  // Dirty tracking
  const isDirty =
    description !== (study.description ?? "") ||
    sessionInstruction !== (study.session_instruction ?? "") ||
    defaultImageViewer !== (study.default_image_viewer ?? "native");

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const invalidateStudy = () => {
    queryClient.invalidateQueries({
      queryKey: ["admin", "studies", String(study.id)],
    });
    queryClient.invalidateQueries({ queryKey: ["admin", "studies"] });
  };

  // Save settings mutation
  const saveSettings = useMutation({
    mutationFn: () =>
      api.put(`/api/admin/studies/${study.id}/settings`, {
        name: study.name,
        description,
        session_instruction: sessionInstruction,
        default_image_viewer: defaultImageViewer,
      }),
    onSuccess: () => {
      toast.success("Settings saved.");
      invalidateStudy();
    },
    onError: () => {
      toast.error("Failed to save settings.");
    },
  });

  // Save ref for unsaved-changes warning (must be after saveSettings declaration)
  const handleSave = useCallback(async () => {
    await saveSettings.mutateAsync();
  }, [saveSettings]);

  useEffect(() => {
    if (saveRef) saveRef.current = handleSave;
    return () => { if (saveRef) saveRef.current = null; };
  }, [saveRef, handleSave]);

  // Upload PDF mutation
  const uploadPdf = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("protocol_pdf", file);
      return api.upload(`/api/admin/studies/${study.id}/upload-pdf`, formData);
    },
    onSuccess: () => {
      toast.success("Protocol PDF uploaded.");
      invalidateStudy();
    },
    onError: () => {
      toast.error("Failed to upload PDF.");
    },
  });

  // Delete mutation
  const deleteStudy = useMutation({
    mutationFn: () => api.delete(`/api/admin/studies/${study.id}`),
    onSuccess: () => {
      toast.success("Study deleted.");
      queryClient.invalidateQueries({ queryKey: ["admin", "studies"] });
      navigate("/admin/studies");
    },
    onError: () => {
      toast.error("Failed to delete study.");
    },
  });

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadPdf.mutate(file);
    }
    e.target.value = "";
  };

  return (
    <div className="space-y-4">
      {/* General Settings */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-1.5 text-base">
            <Pencil className="size-4" />
            General Settings
          </CardTitle>
          <CardDescription className="text-sm">
            Description, session instructions, and study protocol.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-sm">
              <Label className="text-sm" htmlFor="description">Description</Label>
              <span className="text-muted-foreground/40">·</span>
              <span className="text-muted-foreground font-normal">Shown to participants at study selection</span>
            </div>
            <div className="pl-4">
              <Input
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional study description..."
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-sm">
              <Label className="text-sm">Session Instruction</Label>
              <span className="text-muted-foreground/40">·</span>
              <span className="text-muted-foreground font-normal">Shown to participants when starting evaluation</span>
            </div>
            <div className="pl-4">
              <RichTextEditor
                key={study.id}
                value={sessionInstruction}
                onChange={setSessionInstruction}
                placeholder="Instructions shown to participants during evaluation..."
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-sm">
              <Label className="text-sm">Default Image Viewer</Label>
              <span className="text-muted-foreground/40">·</span>
              <span className="text-muted-foreground font-normal">Controls which viewer participants see for this study</span>
            </div>
            <div className="pl-4">
              <Select
                value={defaultImageViewer}
                onValueChange={(value) => setDefaultImageViewer(value as "native" | "xopat")}
              >
                <SelectTrigger className="w-[180px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="native">Native viewer</SelectItem>
                  <SelectItem value="xopat">XOpat viewer</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Study Protocol */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-sm">
              <Label className="text-sm">Study Protocol</Label>
              <span className="text-muted-foreground/40">·</span>
              <span className="text-muted-foreground font-normal">Can be downloaded by participants</span>
            </div>
            <div className="pl-4">
            <div className="flex items-center gap-3 rounded-md border-2 border-dashed border-border px-4 py-4">
              <Upload className="h-4 w-4 text-muted-foreground/40 shrink-0" />
              <p className="text-xs text-muted-foreground flex-1">
                {study.protocol_pdf_path ? "PDF uploaded" : "No PDF uploaded"}
              </p>
              {study.protocol_pdf_path && (
                <Button variant="outline" size="sm" asChild>
                  <a
                    href={`/api/admin/studies/${study.id}/download-pdf`}
                    download
                  >
                    <Download className="h-3.5 w-3.5" />
                    Download
                  </a>
                </Button>
              )}
              <Label htmlFor="pdf-upload" className="cursor-pointer">
                <Button
                  variant="outline"
                  size="sm"
                  asChild
                  disabled={uploadPdf.isPending}
                >
                  <span>
                    {uploadPdf.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Upload className="h-3.5 w-3.5" />
                    )}
                    Upload PDF
                  </span>
                </Button>
              </Label>
              <input
                id="pdf-upload"
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={handleFileUpload}
              />
            </div>
            </div>
          </div>

          <Button
            size="sm"
            onClick={() => saveSettings.mutate()}
            disabled={saveSettings.isPending}
          >
            {saveSettings.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="h-3.5 w-3.5" />
            )}
            Save Settings
          </Button>
        </CardContent>
      </Card>

      {/* Danger Zone */}
      <Card className="border-destructive/20 bg-destructive/5">
        <CardHeader className="pb-3">
          <CardTitle className="text-base text-destructive">Danger Zone</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex w-full items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Once deleted, all data will be permanently removed.
            </p>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm">
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete Study
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete Study</AlertDialogTitle>
                  <AlertDialogDescription>
                    Are you sure you want to delete{" "}
                    <span className="font-medium">{study.name}</span>? This
                    will permanently remove the study, its dataset, and all
                    associated ratings. This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    variant="destructive"
                    onClick={() => deleteStudy.mutate()}
                  >
                    Delete Study
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
