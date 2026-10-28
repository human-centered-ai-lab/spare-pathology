import { useState, useRef, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import type { DatasetsOverview } from "@/types";
import { toast } from "sonner";
import {
  Upload,
  FolderOpen,
  Database,
  Trash2,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Info,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB

interface UploadState {
  datasetName: string;
  sanitizedName: string;
  uploadId: string;
  fileCount: number;
  imageCount: number;
  totalSize: number;
  uploading: boolean;
  filesCompleted: number;
  bytesUploaded: number;
  totalBytes: number;
  error: string | null;
  validationResult: string | null;
  nameExists: boolean | null;
  checking: boolean;
  hasMetadataCsv: boolean;
  unreferencedFiles: string[];
}

function initialUploadState(): UploadState {
  return {
    datasetName: "",
    sanitizedName: "",
    uploadId: "",
    fileCount: 0,
    imageCount: 0,
    totalSize: 0,
    uploading: false,
    filesCompleted: 0,
    bytesUploaded: 0,
    totalBytes: 0,
    error: null,
    validationResult: null,
    nameExists: null,
    checking: false,
    hasMetadataCsv: false,
    unreferencedFiles: [],
  };
}

const IMAGE_EXTENSIONS = new Set([
  ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
]);

function isImageFile(name: string): boolean {
  const dot = name.lastIndexOf(".");
  if (dot === -1) return false;
  return IMAGE_EXTENSIONS.has(name.slice(dot).toLowerCase());
}

function parseSimpleCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];

    if (inQuotes) {
      if (ch === '"') {
        // Escaped quote ("")
        if (i + 1 < text.length && text[i + 1] === '"') {
          cell += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        cell += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
      continue;
    }
    if (ch === ",") {
      row.push(cell.trim());
      cell = "";
      continue;
    }
    if (ch === "\n") {
      row.push(cell.trim());
      if (row.some((value) => value.length > 0)) {
        rows.push(row);
      }
      row = [];
      cell = "";
      continue;
    }
    if (ch !== "\r") {
      cell += ch;
    }
  }

  row.push(cell.trim());
  if (row.some((value) => value.length > 0)) {
    rows.push(row);
  }

  return rows;
}

function generateUploadId(): string {
  return `upload_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export default function ImagesPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [uploadState, setUploadState] = useState<UploadState>(
    initialUploadState(),
  );
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<DatasetsOverview | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [sortKey, setSortKey] = useState<string>("dataset_name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
    setPage(0);
  };

  // Fetch datasets overview
  const { data: datasets, isLoading: datasetsLoading } = useQuery<DatasetsOverview[]>(
    {
      queryKey: ["admin", "images", "datasets-overview"],
      queryFn: () =>
        api.get<DatasetsOverview[]>("/api/admin/images/datasets-overview"),
    },
  );

  const deleteMutation = useMutation<void, Error, string>({
    mutationFn: (datasetName) =>
      api.post("/api/admin/images/delete-dataset", { dataset_name: datasetName }),
    onSuccess: () => {
      toast.success("Dataset deleted successfully");
      setDeleteTarget(null);
      queryClient.invalidateQueries({
        queryKey: ["admin", "images", "datasets-overview"],
      });
    },
    onError: (err) => {
      toast.error(err.message || "Failed to delete dataset");
    },
  });

  function generateDefaultName(): string {
    const existingNames = new Set(
      (datasets ?? []).map((d) => d.dataset_name),
    );
    const base = "new_dataset";
    if (!existingNames.has(base)) return base;
    for (let i = 1; ; i++) {
      const candidate = `${base}_${i}`;
      if (!existingNames.has(candidate)) return candidate;
    }
  }

  const handleFolderSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      const fileList = Array.from(files);
      setSelectedFiles(fileList);

      const defaultName = generateDefaultName();
      const totalSize = fileList.reduce((sum, f) => sum + f.size, 0);

      // Separate image files and find metadata.csv (root level only)
      const imageFiles: string[] = [];
      let metadataFile: File | null = null;
      for (const f of fileList) {
        const parts = f.webkitRelativePath.split("/");
        const fileName = parts.length > 1 ? parts[parts.length - 1] : f.name;
        if (parts.length === 2 && fileName === "metadata.csv") {
          metadataFile = f;
        } else if (isImageFile(fileName)) {
          imageFiles.push(fileName);
        }
      }

      const hasMetadataCsv = metadataFile !== null;

      // Parse metadata.csv and check image references
      let unreferencedFiles: string[] = [];
      if (metadataFile) {
        try {
          const text = await metadataFile.text();
          const rows = parseSimpleCsv(text);
          if (rows.length > 0) {
            const header = rows[0];
            const nameIdx = header.indexOf("image_name");
            if (nameIdx !== -1) {
              const referencedNames = new Set<string>();
              for (let i = 1; i < rows.length; i++) {
                const val = rows[i][nameIdx]?.trim();
                if (val) {
                  referencedNames.add(val);
                  // Also add without extension for matching
                  const dot = val.lastIndexOf(".");
                  if (dot !== -1) referencedNames.add(val.slice(0, dot));
                }
              }
              unreferencedFiles = imageFiles.filter((name) => {
                if (referencedNames.has(name)) return false;
                // Check without extension
                const dot = name.lastIndexOf(".");
                if (dot !== -1 && referencedNames.has(name.slice(0, dot)))
                  return false;
                return true;
              });
            }
          }
        } catch {
          // If we can't parse, let the backend catch it
        }
      }

      setUploadState({
        ...initialUploadState(),
        datasetName: defaultName,
        uploadId: generateUploadId(),
        fileCount: fileList.length,
        imageCount: imageFiles.length,
        totalSize,
        nameExists: false,
        hasMetadataCsv,
        unreferencedFiles,
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [datasets],
  );

  // Re-check name availability when user edits the dataset name
  useEffect(() => {
    const name = uploadState.datasetName.trim();
    if (!name || selectedFiles.length === 0) return;

    let cancelled = false;
    const timeout = setTimeout(async () => {
      setUploadState((prev) => ({ ...prev, checking: true }));
      try {
        const result = await api.post<{
          exists: boolean;
          dataset_name: string;
        }>("/api/admin/images/check-dataset-name", { dataset_name: name });
        if (cancelled) return;
        setUploadState((prev) => ({
          ...prev,
          sanitizedName: result.dataset_name,
          nameExists: result.exists,
          checking: false,
        }));
      } catch {
        if (cancelled) return;
        setUploadState((prev) => ({
          ...prev,
          nameExists: null,
          checking: false,
        }));
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploadState.datasetName, datasets]);

  const handleUpload = useCallback(async () => {
    if (selectedFiles.length === 0) return;

    setUploadState((prev) => ({
      ...prev,
      uploading: true,
      filesCompleted: 0,
      bytesUploaded: 0,
      totalBytes: prev.totalSize,
      error: null,
      validationResult: null,
    }));

    try {
      for (let fileIdx = 0; fileIdx < selectedFiles.length; fileIdx++) {
        const file = selectedFiles[fileIdx];
        const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

        // Compute the relative path within the dataset folder
        const relativePath = file.webkitRelativePath
          ? file.webkitRelativePath.split("/").slice(1).join("/")
          : file.name;

        for (let chunkIdx = 0; chunkIdx < totalChunks; chunkIdx++) {
          const start = chunkIdx * CHUNK_SIZE;
          const end = Math.min(start + CHUNK_SIZE, file.size);
          const chunk = file.slice(start, end);

          const formData = new FormData();
          formData.append("chunk", chunk);
          formData.append("file_path", relativePath);
          formData.append("chunk_index", String(chunkIdx));
          formData.append("total_chunks", String(totalChunks));
          formData.append("dataset_name", uploadState.datasetName);
          formData.append("upload_id", uploadState.uploadId);

          await api.upload("/api/admin/images/upload-chunk", formData);

          setUploadState((prev) => ({
            ...prev,
            bytesUploaded: prev.bytesUploaded + (end - start),
          }));
        }

        setUploadState((prev) => ({
          ...prev,
          filesCompleted: prev.filesCompleted + 1,
        }));
      }

      // Signal upload complete
      const completeResult = await api.post<{ status: string; validation?: { valid: boolean; errors: string[] } }>(
        "/api/admin/images/upload-complete",
        { upload_id: uploadState.uploadId, dataset_name: uploadState.datasetName },
      );

      const valid = completeResult.validation?.valid ?? true;
      const validationErrors = completeResult.validation?.errors ?? [];

      setUploadState((prev) => ({
        ...prev,
        uploading: false,
        validationResult: valid ? "Upload completed successfully" : null,
        error: !valid ? validationErrors.join(" ") : null,
      }));

      if (valid) {
        toast.success("Upload completed successfully");
      } else {
        toast.error("Upload completed with validation errors");
      }

      // Invalidate datasets overview
      queryClient.invalidateQueries({
        queryKey: ["admin", "images", "datasets-overview"],
      });

      // Reset file input
      if (folderInputRef.current) {
        folderInputRef.current.value = "";
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Upload failed";
      setUploadState((prev) => ({
        ...prev,
        uploading: false,
        error: message,
      }));
      toast.error(message);
    }
  }, [selectedFiles, uploadState.datasetName, uploadState.uploadId, queryClient]);

  const uploadProgress =
    uploadState.totalBytes > 0
      ? (uploadState.bytesUploaded / uploadState.totalBytes) * 100
      : 0;

  function canDelete(dataset: DatasetsOverview): boolean {
    return dataset.referenced_by_studies === 0;
  }

  return (
    <div className="space-y-4">
      <h1 className="flex items-center gap-2 text-2xl font-bold"><Database className="size-6" />Datasets</h1>

      {/* Upload Section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Upload className="size-4" />
            Upload a Dataset
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Upload instructions */}
          <div className="rounded-md border border-border/60 bg-muted/30 p-4 text-sm space-y-4">
            <div className="flex items-center gap-2 font-medium">
              <Info className="size-4 text-muted-foreground" />
              Required folder structure
            </div>
            <div className="text-muted-foreground space-y-3">
              <p>
                Select a folder containing your image files and a{" "}
                <code className="rounded bg-muted px-1 py-0.5 text-xs font-mono">metadata.csv</code>{" "}
                file.
              </p>
              <div className="text-xs space-y-0.5 font-mono text-foreground/70">
                <p>my_dataset/</p>
                <p className="pl-4">metadata.csv</p>
                <p className="pl-4">image_001.png</p>
                <p className="pl-4">image_002.png</p>
                <p className="pl-4">...</p>
              </div>
              <p className="text-xs">
                Example <code className="rounded bg-muted px-1 py-0.5 font-mono">metadata.csv</code> — additional columns become attributes usable for<br />filtering the data and doing statistical analysis on the evaluation results:
              </p>
              <div className="overflow-x-auto w-fit rounded border border-border/60 bg-background">
                <table className="text-xs font-mono">
                  <thead>
                    <tr className="border-b border-border/60">
                      <th className="px-3 py-1.5 text-left font-medium text-foreground/70">image_name</th>
                      <th className="px-3 py-1.5 text-left font-medium text-foreground/70">mpp_value</th>
                      <th className="px-3 py-1.5 text-left font-medium text-foreground/70">synthetic</th>
                    </tr>
                  </thead>
                  <tbody className="text-foreground/60">
                    <tr className="border-b border-border/40">
                      <td className="px-3 py-1">image_001</td>
                      <td className="px-3 py-1">0.25</td>
                      <td className="px-3 py-1">false</td>
                    </tr>
                    <tr>
                      <td className="px-3 py-1">image_002</td>
                      <td className="px-3 py-1">0.5</td>
                      <td className="px-3 py-1">true</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Hidden folder input */}
          <input
            ref={folderInputRef}
            type="file"
            /* @ts-expect-error webkitdirectory is non-standard but widely supported */
            webkitdirectory=""
            multiple
            className="hidden"
            onChange={handleFolderSelect}
          />

          <Button
            variant="outline"
            onClick={() => folderInputRef.current?.click()}
            disabled={uploadState.uploading}
          >
            <FolderOpen className="size-4" />
            Select Folder
          </Button>

          {/* Selected folder info */}
          {selectedFiles.length > 0 && !uploadState.uploading && !uploadState.validationResult && (
            <div className="rounded-md border p-4 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="dataset-name" className="text-sm">Dataset Name</Label>
                <Input
                  id="dataset-name"
                  value={uploadState.datasetName}
                  onChange={(e) =>
                    setUploadState((prev) => ({
                      ...prev,
                      datasetName: e.target.value,
                      error: null,
                    }))
                  }
                  className="max-w-xs"
                />
                {uploadState.sanitizedName && uploadState.sanitizedName !== uploadState.datasetName.trim() && (
                  <p className="text-xs text-muted-foreground">
                    Folder name: <code className="rounded bg-muted px-1 py-0.5 font-mono">{uploadState.sanitizedName}</code>
                  </p>
                )}
                {uploadState.checking && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    Checking name availability...
                  </div>
                )}
                {!uploadState.checking && uploadState.nameExists === false && uploadState.datasetName.trim() && (
                  <div className="flex items-center gap-2 text-sm text-green-600">
                    <CheckCircle2 className="size-4" />
                    Name is available
                  </div>
                )}
                {!uploadState.checking && uploadState.nameExists === true && (
                  <div className="flex items-center gap-2 text-sm text-amber-600">
                    <AlertTriangle className="size-4" />
                    A dataset with this name already exists.
                  </div>
                )}
              </div>

              <div className="flex items-center gap-6 text-sm text-muted-foreground">
                <span>{uploadState.imageCount} image{uploadState.imageCount !== 1 ? "s" : ""}</span>
                <span>{formatBytes(uploadState.totalSize)}</span>
                {uploadState.hasMetadataCsv ? (
                  <span className="flex items-center gap-1 text-green-600">
                    <CheckCircle2 className="size-3.5" />
                    metadata.csv found
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-destructive">
                    <AlertTriangle className="size-3.5" />
                    metadata.csv not found
                  </span>
                )}
              </div>

              {uploadState.unreferencedFiles.length > 0 && (
                <div className="flex items-start gap-2 text-sm text-destructive">
                  <AlertTriangle className="size-4 mt-0.5 shrink-0" />
                  <div>
                    <p>
                      {uploadState.unreferencedFiles.length} image{uploadState.unreferencedFiles.length !== 1 ? "s" : ""} not
                      referenced in metadata.csv:
                    </p>
                    <p className="font-mono text-xs mt-1">
                      {uploadState.unreferencedFiles.slice(0, 5).join(", ")}
                      {uploadState.unreferencedFiles.length > 5 &&
                        ` and ${uploadState.unreferencedFiles.length - 5} more`}
                    </p>
                  </div>
                </div>
              )}

              <Button
                onClick={handleUpload}
                disabled={
                  uploadState.checking ||
                  uploadState.uploading ||
                  uploadState.nameExists === true ||
                  !uploadState.datasetName.trim() ||
                  !uploadState.hasMetadataCsv ||
                  uploadState.unreferencedFiles.length > 0
                }
              >
                <Upload className="size-4" />
                Upload
              </Button>
            </div>
          )}

          {/* Upload progress */}
          {uploadState.uploading && (
            <div className="rounded-md border p-4 space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span>
                  Uploading {uploadState.datasetName}...
                </span>
                <span className="text-muted-foreground">
                  {uploadState.filesCompleted} / {uploadState.fileCount} files
                </span>
              </div>
              <Progress value={uploadProgress} className="h-2" />
              <p className="text-xs text-muted-foreground">
                {formatBytes(uploadState.bytesUploaded)} /{" "}
                {formatBytes(uploadState.totalBytes)}
              </p>
            </div>
          )}

          {/* Error */}
          {uploadState.error && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertTriangle className="size-4" />
              {uploadState.error}
            </div>
          )}

          {/* Validation result */}
          {uploadState.validationResult && (
            <div className="flex items-center gap-2 text-sm text-green-600">
              <CheckCircle2 className="size-4" />
              {uploadState.validationResult}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Datasets Overview Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Database className="size-4" />
            Available Datasets
          </CardTitle>
        </CardHeader>
        <CardContent className="px-6 pb-6 pt-0">
          {datasetsLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : !datasets || datasets.length === 0 ? (
            <p className="text-muted-foreground text-sm py-8 text-center">
              No datasets uploaded yet.
            </p>
          ) : (() => {
            const sorted = [...datasets].sort((a, b) => {
              const dir = sortDir === "asc" ? 1 : -1;
              switch (sortKey) {
                case "dataset_name":
                  return a.dataset_name.localeCompare(b.dataset_name) * dir;
                case "image_count":
                  return (a.image_count - b.image_count) * dir;
                case "attributes":
                  return (a.attribute_names.length - b.attribute_names.length) * dir;
                case "referenced_by":
                  return (a.referenced_by_studies - b.referenced_by_studies) * dir;
                default:
                  return 0;
              }
            });
            const total = sorted.length;
            const totalPages = Math.max(1, Math.ceil(total / pageSize));
            const paged = sorted.slice(page * pageSize, (page + 1) * pageSize);

            return (
            <>
            <Table>
              <TableHeader>
                <TableRow>
                  {([
                    ["dataset_name", "Name"],
                    ["image_count", "Images"],
                    ["attributes", "Attributes"],
                    ["referenced_by", "Referenced By"],
                  ] as const).map(([key, label]) => (
                    <TableHead key={key}>
                      <button
                        className="inline-flex items-center gap-1 hover:text-foreground transition-colors"
                        onClick={() => handleSort(key)}
                      >
                        {label}
                        {sortKey === key ? (
                          sortDir === "asc" ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />
                        ) : (
                          <ArrowUpDown className="size-3.5 opacity-30" />
                        )}
                      </button>
                    </TableHead>
                  ))}
                  <TableHead className="w-0 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paged.map((dataset) => (
                  <TableRow
                    key={dataset.dataset_name}
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() =>
                      navigate(`/admin/images/${encodeURIComponent(dataset.dataset_name)}`)
                    }
                    onKeyDown={(event) => {
                      if (event.key !== "Enter" && event.key !== " ") return;
                      event.preventDefault();
                      navigate(`/admin/images/${encodeURIComponent(dataset.dataset_name)}`);
                    }}
                    tabIndex={0}
                  >
                    <TableCell className="font-medium">
                      {dataset.dataset_name}
                    </TableCell>
                    <TableCell>{dataset.image_count}</TableCell>
                    <TableCell>
                      {dataset.attribute_names.length > 0 ? (
                        <span className="text-sm">
                          {dataset.attribute_names.join(", ")}
                        </span>
                      ) : (
                        <span className="text-muted-foreground text-sm">
                          None
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      {dataset.referenced_by_studies > 0 ? (
                        <span className="text-sm">
                          {dataset.referenced_by_studies} {dataset.referenced_by_studies !== 1 ? "studies" : "study"}
                        </span>
                      ) : (
                        <span className="text-muted-foreground text-sm">
                          None
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="inline-block">
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                className="h-8 w-8 text-muted-foreground hover:text-destructive"
                                disabled={!canDelete(dataset)}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setDeleteTarget(dataset);
                                }}
                              >
                                <Trash2 className="size-4" />
                              </Button>
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            {canDelete(dataset)
                              ? "Delete dataset"
                              : `Cannot delete: used by ${dataset.referenced_by_studies} ${dataset.referenced_by_studies !== 1 ? "studies" : "study"}`}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="flex items-center justify-between pt-4 border-t mt-2">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <span>Rows per page</span>
                <Select
                  value={String(pageSize)}
                  onValueChange={(val) => { setPageSize(Number(val)); setPage(0); }}
                >
                  <SelectTrigger className="h-8 w-[70px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="20">20</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <span>{page * pageSize + 1}–{Math.min((page + 1) * pageSize, total)} of {total}</span>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setPage((p) => p - 1)}
                  disabled={page === 0}
                >
                  <ChevronLeft className="size-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page >= totalPages - 1}
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
            </>
            );
          })()}
        </CardContent>
      </Card>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Dataset</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete the dataset &quot;{deleteTarget?.dataset_name}
              &quot;? This will remove all associated image files. This action
              cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (deleteTarget) {
                  deleteMutation.mutate(deleteTarget.dataset_name);
                }
              }}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}
