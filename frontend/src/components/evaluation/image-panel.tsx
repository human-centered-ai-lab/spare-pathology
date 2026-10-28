import { useEffect, useRef, useState } from "react";
import { Minus, Plus } from "lucide-react";
import {
  TransformComponent,
  TransformWrapper,
  useControls,
  useTransformComponent,
  useTransformContext,
} from "react-zoom-pan-pinch";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { XopatImagePanel } from "@/components/evaluation/xopat-image-panel";
import type { ImageData } from "@/types";

interface ImagePanelProps {
  imageData: ImageData | null;
  loading: boolean;
  viewerMode?: "native" | "xopat";
  shortcutMode?: "none" | "navigation" | "evaluation";
}

interface ImageZoomSurfaceProps {
  imageData: ImageData;
  imageUrl: string;
  naturalWidth: number;
  naturalHeight: number;
  fitScale: number;
  actualScale: number;
  maxScale: number;
}

function ImageZoomControls({
  fitScale,
  actualScale,
  maxScale,
}: Pick<ImageZoomSurfaceProps, "fitScale" | "actualScale" | "maxScale">) {
  const scale = useTransformComponent(({ state }) => state.scale);
  const { centerView, zoomIn, zoomOut } = useControls();

  const scalePct = Math.round((scale / actualScale) * 100);
  const nearFit = Math.abs(scale - fitScale) < 0.01;
  const nearActual = Math.abs(scale - actualScale) < 0.01;

  return (
    <div className="absolute right-3 top-3 z-10 flex items-center gap-1 rounded-md border border-border/70 bg-card/90 p-1 shadow-sm backdrop-blur">
      <span className="px-2 text-xs tabular-nums text-muted-foreground">
        {scalePct}%
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={() => zoomOut(0.2, 0)}
        disabled={nearFit}
        title="Zoom out"
      >
        <Minus className="size-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={() => zoomIn(0.2, 0)}
        disabled={scale >= maxScale - 0.01}
        title="Zoom in"
      >
        <Plus className="size-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-8 px-2 text-xs"
        onClick={() => centerView(fitScale, 0)}
        disabled={nearFit}
      >
        Fit
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-8 px-2 text-xs"
        onClick={() => centerView(actualScale, 0)}
        disabled={nearActual}
      >
        100%
      </Button>
    </div>
  );
}

function ZoomableImageCanvas({
  imageData,
  imageUrl,
  naturalWidth,
  naturalHeight,
  fitScale,
  actualScale,
}: Omit<ImageZoomSurfaceProps, "maxScale">) {
  const instance = useTransformContext();
  const { centerView } = useControls();

  const handleToggleZoom = () => {
    const currentScale = instance.state.scale;
    const nearFit = Math.abs(currentScale - fitScale) < 0.01;
    centerView(nearFit ? actualScale : fitScale, 0);
  };

  return (
    <TransformComponent
      wrapperClass="!h-full !w-full cursor-grab active:cursor-grabbing"
      wrapperStyle={{ width: "100%", height: "100%" }}
      wrapperProps={{ onDoubleClick: handleToggleZoom }}
      contentClass="will-change-transform"
      contentStyle={{
        width: `${naturalWidth}px`,
        height: `${naturalHeight}px`,
      }}
    >
      <img
        src={imageUrl}
        alt={`Image ${imageData.position}`}
        className="block h-full w-full max-h-none max-w-none select-none"
        draggable={false}
      />
    </TransformComponent>
  );
}

function ImageZoomSurface({
  imageData,
  imageUrl,
  naturalWidth,
  naturalHeight,
  fitScale,
  actualScale,
  maxScale,
}: ImageZoomSurfaceProps) {
  return (
    <TransformWrapper
      initialScale={fitScale}
      minScale={fitScale}
      maxScale={maxScale}
      centerOnInit
      limitToBounds
      smooth={false}
      wheel={{ step: 0.12 }}
      pinch={{ step: 5 }}
      panning={{ velocityDisabled: true }}
      trackPadPanning={{ velocityDisabled: true }}
      zoomAnimation={{ disabled: true }}
      doubleClick={{ disabled: true }}
    >
      <ImageZoomControls
        fitScale={fitScale}
        actualScale={actualScale}
        maxScale={maxScale}
      />
      <ZoomableImageCanvas
        imageData={imageData}
        imageUrl={imageUrl}
        naturalWidth={naturalWidth}
        naturalHeight={naturalHeight}
        fitScale={fitScale}
        actualScale={actualScale}
      />
    </TransformWrapper>
  );
}

export function ImagePanel({
  imageData,
  loading,
  viewerMode = "native",
  shortcutMode = "none",
}: ImagePanelProps) {
  if (viewerMode === "xopat") {
    return (
      <XopatImagePanel
        imageData={imageData}
        loading={loading}
        shortcutMode={shortcutMode}
      />
    );
  }

  return <NativeImagePanel imageData={imageData} loading={loading} />;
}

function NativeImagePanel({ imageData, loading }: Omit<ImagePanelProps, "viewerMode">) {

  const imageUrl = imageData?.image_url;
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const [imageState, setImageState] = useState<{
    url: string | null;
    metrics: {
      naturalWidth: number;
      naturalHeight: number;
    } | null;
    failed: boolean;
  }>({
    url: null,
    metrics: null,
    failed: false,
  });
  const [viewerSize, setViewerSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const node = viewerRef.current;
    if (!node) return;

    const updateSize = () => {
      setViewerSize({
        width: node.clientWidth,
        height: node.clientHeight,
      });
    };

    updateSize();

    const observer = new ResizeObserver(updateSize);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!imageUrl) return;

    let cancelled = false;
    const image = new Image();

    image.onload = () => {
      if (cancelled) return;
      setImageState({
        url: imageUrl,
        metrics: {
          naturalWidth: image.naturalWidth,
          naturalHeight: image.naturalHeight,
        },
        failed: false,
      });
    };

    image.onerror = () => {
      if (cancelled) return;
      setImageState({
        url: imageUrl,
        metrics: null,
        failed: true,
      });
    };

    image.src = imageUrl;

    return () => {
      cancelled = true;
    };
  }, [imageUrl]);

  const imageMetrics = imageState.url === imageUrl ? imageState.metrics : null;
  const loadFailed = imageState.url === imageUrl && imageState.failed;

  const fitScale =
    imageMetrics && viewerSize.width > 0 && viewerSize.height > 0
      ? Math.min(
        viewerSize.width / imageMetrics.naturalWidth,
        viewerSize.height / imageMetrics.naturalHeight,
        1,
      )
      : null;
  const actualScale = 1;
  const maxScale = actualScale;
  const viewerKey =
    imageUrl && fitScale
      ? `${imageUrl}:${Math.round(fitScale * 10000)}`
      : imageUrl ?? "image-viewer";
  const viewerReady = Boolean(imageUrl) && fitScale !== null && imageMetrics !== null;

  return (
    <div className="flex flex-1 flex-col overflow-hidden bg-secondary/30">
      <div className="flex flex-1 overflow-hidden p-6">
        <div
          ref={viewerRef}
          className="relative flex-1 overflow-hidden rounded-md border border-border/50 bg-background/60"
        >
          {loading || !imageData ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 p-8">
              <Skeleton className="aspect-square w-full max-w-lg" />
              <Skeleton className="h-4 w-32" />
            </div>
          ) : loadFailed ? (
            <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">
              Failed to load image.
            </div>
          ) : !viewerReady || !imageUrl ? (
            <div className="flex h-full items-center justify-center p-8">
              <Skeleton className="aspect-square w-full max-w-lg" />
            </div>
          ) : (
            <ImageZoomSurface
              key={viewerKey}
              imageData={imageData}
              imageUrl={imageUrl}
              naturalWidth={imageMetrics.naturalWidth}
              naturalHeight={imageMetrics.naturalHeight}
              fitScale={fitScale}
              actualScale={actualScale}
              maxScale={maxScale}
            />
          )}
        </div>
      </div>
    </div>
  );
}
