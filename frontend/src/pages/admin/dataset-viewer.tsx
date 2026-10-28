import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "@/api/client";
import { ImagePanel } from "@/components/evaluation/image-panel";
import { ImageSidebar } from "@/components/evaluation/image-sidebar";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import type {
  AttributeSchema,
  ImageData,
  ImageListItem,
  PaginatedBrowse,
} from "@/types";

const EMPTY_DATASET_IMAGES: PaginatedBrowse["items"] = [];
const VIEWER_MODE_STORAGE_KEY = "admin_dataset_viewer_mode";

export default function AdminDatasetViewerPage() {
  const { datasetName: datasetNameParam } = useParams<{ datasetName: string }>();
  const datasetName = datasetNameParam ? decodeURIComponent(datasetNameParam) : "";
  const navigate = useNavigate();
  const [selectedImagePath, setSelectedImagePath] = useState<string | null>(null);
  const [viewerMode, setViewerMode] = useState<"native" | "xopat">(() => {
    if (typeof window === "undefined") return "native";
    return window.localStorage.getItem(VIEWER_MODE_STORAGE_KEY) === "xopat"
      ? "xopat"
      : "native";
  });

  useEffect(() => {
    window.localStorage.setItem(VIEWER_MODE_STORAGE_KEY, viewerMode);
  }, [viewerMode]);

  const imagesQuery = useQuery<PaginatedBrowse, Error>({
    queryKey: ["admin", "datasets", datasetName, "viewer"],
    queryFn: () =>
      api.get<PaginatedBrowse>(
        `/api/admin/datasets/${encodeURIComponent(datasetName)}/images?all=true`,
      ),
    enabled: Boolean(datasetName),
  });

  const attributesQuery = useQuery<AttributeSchema[], Error>({
    queryKey: ["admin", "datasets", datasetName, "attributes"],
    queryFn: () =>
      api.get<AttributeSchema[]>(
        `/api/admin/datasets/${encodeURIComponent(datasetName)}/attributes`,
      ),
    enabled: Boolean(datasetName),
  });

  const datasetImages = imagesQuery.data?.items ?? EMPTY_DATASET_IMAGES;
  const attributeColumns = attributesQuery.data?.map((attribute) => attribute.name);
  const currentIndex = datasetImages.findIndex(
    (image) => image.image_path === selectedImagePath,
  );
  const currentPosition = currentIndex >= 0 ? currentIndex + 1 : 1;

  const imageList = useMemo<ImageListItem[]>(
    () =>
      datasetImages.map((image, index) => ({
        position: index + 1,
        dataset_image_id: index + 1,
        image_name: image.image_name,
        status: "not_opened",
        visible_attributes: image.attributes,
      })),
    [datasetImages],
  );

  const currentImageData: ImageData | null = useMemo(() => {
    const image = datasetImages[currentPosition - 1];
    if (!image) return null;

    return {
      dataset_image_id: currentPosition,
      position: currentPosition,
      image_url: `/api/admin/images/serve/${image.image_path}`,
      total_images: datasetImages.length,
      rating: null,
      visible_attributes: image.attributes,
      xopat_slide_id: image.xopat_slide_id,
      xopat_microns: image.xopat_microns,
    };
  }, [currentPosition, datasetImages]);

  const handleSelect = useCallback((position: number) => {
    const image = datasetImages[position - 1];
    if (!image) return;
    setSelectedImagePath(image.image_path);
  }, [datasetImages]);

  const handlePrev = useCallback(() => {
    const image = datasetImages[currentPosition - 2];
    if (!image) return;
    setSelectedImagePath(image.image_path);
  }, [currentPosition, datasetImages]);

  const handleNext = useCallback(() => {
    const image = datasetImages[currentPosition];
    if (!image) return;
    setSelectedImagePath(image.image_path);
  }, [currentPosition, datasetImages]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (target.tagName === "TEXTAREA" || target.tagName === "INPUT") return;
      if (target.isContentEditable) return;

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        handlePrev();
        return;
      }

      if (event.key === "ArrowRight") {
        event.preventDefault();
        handleNext();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleNext, handlePrev]);

  if (!datasetName) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">Dataset not found.</p>
        <Button variant="outline" onClick={() => navigate("/admin/images")}>
          <ArrowLeft className="size-4" />
          Back to Datasets
        </Button>
      </div>
    );
  }

  if (imagesQuery.isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-muted-foreground">Loading dataset viewer...</div>
      </div>
    );
  }

  if (imagesQuery.isError) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">
          {imagesQuery.error.message || "Failed to load dataset."}
        </p>
        <Button variant="outline" onClick={() => navigate("/admin/images")}>
          <ArrowLeft className="size-4" />
          Back to Datasets
        </Button>
      </div>
    );
  }

  if (datasetImages.length === 0) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">This dataset has no images.</p>
        <Button variant="outline" onClick={() => navigate("/admin/images")}>
          <ArrowLeft className="size-4" />
          Back to Datasets
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <header className="flex items-center gap-3 border-b border-border px-4 py-3">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => navigate("/admin/images")}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <Separator orientation="vertical" className="h-5" />
        <h1 className="text-sm font-semibold text-foreground">{datasetName}</h1>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Viewer</span>
          <Select
            value={viewerMode}
            onValueChange={(value) => setViewerMode(value as "native" | "xopat")}
          >
            <SelectTrigger className="h-8 w-[110px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="native">Native</SelectItem>
              <SelectItem value="xopat">XOpat</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <ImageSidebar
          images={imageList}
          currentPosition={currentPosition}
          onSelect={handleSelect}
          loading={imagesQuery.isLoading}
          attributeColumns={attributeColumns}
          imageColumnLabel="File"
          imageColumnSort="label"
          getImageLabel={(image) => image.image_name}
          showStatusIndicator={false}
          className="w-[34rem] min-w-[24rem] max-w-[70vw]"
          tableClassName="min-w-full"
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <ImagePanel
            imageData={currentImageData}
            loading={imagesQuery.isLoading}
            viewerMode={viewerMode}
            shortcutMode="navigation"
          />

          <footer className="flex items-center justify-between border-t border-border bg-card px-4 py-2.5">
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={handlePrev}
                disabled={currentPosition <= 1}
                title="Previous image"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-xs text-muted-foreground">
                {currentPosition} / {datasetImages.length}
              </span>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={handleNext}
                disabled={currentPosition >= datasetImages.length}
                title="Next image"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            <span className="text-xs text-muted-foreground">
              {datasetImages.length} images
            </span>
          </footer>
        </div>
      </div>
    </div>
  );
}
