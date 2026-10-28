import { useState, useCallback, useRef, type CSSProperties } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  DndContext,
  DragOverlay,
  useDraggable,
  useDroppable,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  AlertTriangle,
  Plus,
  Minus,
  GripVertical,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import type {
  BrowseImage,
  PaginatedBrowse,
  PaginatedDatasetImages,
  AttributeSchema,
  ToggleResponse,
  DatasetStats,
} from "@/types";
import { api } from "@/api/client";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { CompositionChart } from "@/components/charts/composition-chart";
import { useMarqueeSelect } from "./use-marquee-select";
import type { MarqueeRect } from "./use-marquee-select";

const LEFT_PER_PAGE = 50;
const RIGHT_PER_PAGE = 50;
const DEFAULT_LEFT_THUMB = 128;
const DEFAULT_RIGHT_THUMB = 72;
const THUMB_MIN = 64;
const THUMB_MAX = 256;
const THUMB_STEP = 8;
const PAGE_SIZES = [25, 50, 100, 200];

interface DatasetOption {
  name: string;
  image_count: number;
}

interface DualPanelBuilderProps {
  studyId: number;
  datasetName: string | null;
  datasets: DatasetOption[];
  onDatasetChange: (name: string) => void;
  datasetDisabled?: boolean;
  disabled?: boolean;
  onChanged?: () => void;
}

export function DualPanelBuilder({
  studyId,
  datasetName,
  datasets,
  onDatasetChange,
  datasetDisabled,
  disabled,
  onChanged,
}: DualPanelBuilderProps) {
  const queryClient = useQueryClient();
  const builderHeight = "calc(100vh - 16rem)";

  // Left panel state
  const [leftPage, setLeftPage] = useState(1);
  const [leftPerPage, setLeftPerPage] = useState(LEFT_PER_PAGE);
  const [filters, setFilters] = useState<Record<string, string[]>>({});
  const [filtersReady, setFiltersReady] = useState(false);
  const [hideAdded, setHideAdded] = useState(false);

  // Thumbnail sizes
  const [leftThumb, setLeftThumb] = useState(DEFAULT_LEFT_THUMB);
  const [rightThumb, setRightThumb] = useState(DEFAULT_RIGHT_THUMB);

  // Right panel state
  const [rightPage, setRightPage] = useState(1);
  const [rightPerPage, setRightPerPage] = useState(RIGHT_PER_PAGE);
  const [showDistribution, setShowDistribution] = useState(false);

  // Multi-select state
  const [selectedLeft, setSelectedLeft] = useState<Set<string>>(new Set());
  const [selectedRight, setSelectedRight] = useState<Set<number>>(new Set());
  const lastLeftIdx = useRef<number | null>(null);
  const lastRightIdx = useRef<number | null>(null);

  // DnD state
  const [dragImage, setDragImage] = useState<BrowseImage | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  // ─── Marquee selection ────────────────────────────────────────────────
  const handleLeftMarquee = useCallback(
    (ids: string[], isAdditive: boolean) => {
      setSelectedLeft((prev) => {
        if (isAdditive) {
          const next = new Set(prev);
          for (const id of ids) next.add(id);
          return next;
        }
        return new Set(ids);
      });
    },
    [],
  );

  const handleRightMarquee = useCallback(
    (ids: string[], isAdditive: boolean) => {
      setSelectedRight((prev) => {
        if (isAdditive) {
          const next = new Set(prev);
          for (const id of ids) next.add(Number(id));
          return next;
        }
        return new Set(ids.map(Number));
      });
    },
    [],
  );

  const {
    setContainerRef: setLeftGridRef,
    onMouseDown: onLeftGridMouseDown,
    rect: leftMarqueeRect,
  } = useMarqueeSelect({
    itemSelector: "[data-select-id]",
    onSelect: handleLeftMarquee,
    disabled: !!disabled,
  });

  const {
    setContainerRef: setRightGridRef,
    onMouseDown: onRightGridMouseDown,
    rect: rightMarqueeRect,
  } = useMarqueeSelect({
    itemSelector: "[data-select-id]",
    onSelect: handleRightMarquee,
    disabled: !!disabled,
  });

  // ─── Dataset attribute schema ──────────────────────────────────────────
  const attrsQuery = useQuery<AttributeSchema[]>({
    queryKey: ["admin", "datasets", datasetName, "attributes"],
    queryFn: () =>
      api.get<AttributeSchema[]>(
        `/api/admin/datasets/${datasetName}/attributes`,
      ),
    enabled: !!datasetName,
  });

  // Initialize filters when attributes load
  const [prevDataset, setPrevDataset] = useState(datasetName);
  if (prevDataset !== datasetName) {
    setPrevDataset(datasetName);
    setFilters({});
    setFiltersReady(false);
    setLeftPage(1);
    setSelectedLeft(new Set());
    setSelectedRight(new Set());
  }

  const attrs = attrsQuery.data;
  if (attrs && attrs.length > 0 && !filtersReady && Object.keys(filters).length === 0) {
    setFiltersReady(true);
    const init: Record<string, string[]> = {};
    for (const a of attrs) init[a.name] = a.values.map(String);
    setFilters(init);
  }

  // ─── Left panel query (browse available images) ────────────────────────
  const leftParams = useCallback(() => {
    const p: Record<string, string> = {
      page: String(leftPage),
      per_page: String(leftPerPage),
      in_study: String(studyId),
    };
    if (hideAdded) p.exclude_selected = "true";
    for (const [k, vals] of Object.entries(filters)) {
      if (vals.length === 0) continue;
      const def = attrs?.find((a) => a.name === k);
      if (def && vals.length === def.values.length) continue;
      p[k] = vals.join(",");
    }
    return p;
  }, [leftPage, leftPerPage, studyId, filters, attrs, hideAdded]);

  const hasEmptyFilter =
    filtersReady && Object.values(filters).some((v) => v.length === 0);

  const leftQuery = useQuery<PaginatedBrowse>({
    queryKey: [
      "admin", "datasets", datasetName, "browse",
      leftPage, leftPerPage, filters, hideAdded, studyId,
    ],
    queryFn: async () => {
      const params = new URLSearchParams(leftParams());
      return api.get<PaginatedBrowse>(
        `/api/admin/datasets/${datasetName}/images?${params}`,
      );
    },
    enabled: !!datasetName && !hasEmptyFilter,
    placeholderData: (prev) => prev,
  });

  const leftItems = hasEmptyFilter ? [] : (leftQuery.data?.items ?? []);
  const leftTotal = hasEmptyFilter ? 0 : (leftQuery.data?.total ?? 0);
  const leftTotalPages = hasEmptyFilter ? 1 : (leftQuery.data?.total_pages ?? 1);

  // ─── Right panel query (study images) ──────────────────────────────────
  const rightQuery = useQuery<PaginatedDatasetImages>({
    queryKey: [
      "admin", "studies", String(studyId), "dataset", "list",
      rightPage, rightPerPage, "sequence_number", "asc",
    ],
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(rightPage),
        per_page: String(rightPerPage),
        sort_by: "sequence_number",
        sort_dir: "asc",
      });
      return api.get<PaginatedDatasetImages>(
        `/api/admin/studies/${studyId}/dataset/list?${params}`,
      );
    },
    placeholderData: (prev) => prev,
  });

  const rightItems = rightQuery.data?.items ?? [];
  const rightTotal = rightQuery.data?.total ?? 0;
  const rightTotalPages = rightQuery.data?.total_pages ?? 1;

  // ─── Stats query ──────────────────────────────────────────────────────
  const statsQuery = useQuery<DatasetStats>({
    queryKey: ["admin", "studies", String(studyId), "dataset", "stats"],
    queryFn: () =>
      api.get<DatasetStats>(`/api/admin/studies/${studyId}/dataset/stats`),
  });

  // ─── Invalidation helpers ──────────────────────────────────────────────
  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["admin", "datasets", datasetName, "browse"] });
    queryClient.invalidateQueries({
      queryKey: ["admin", "studies", String(studyId), "dataset"],
    });
    onChanged?.();
  }, [queryClient, datasetName, studyId, onChanged]);

  // ─── Toggle mutation (single add/remove) ───────────────────────────────
  const toggleMutation = useMutation({
    mutationFn: (img: BrowseImage) =>
      api.post<ToggleResponse>(
        `/api/admin/studies/${studyId}/dataset/toggle`,
        { image_path: img.image_path, attributes: img.attributes },
      ),
    onSettled: invalidateAll,
  });

  // ─── Bulk add mutation ─────────────────────────────────────────────────
  const bulkAddMutation = useMutation({
    mutationFn: (images: { image_path: string; attributes: Record<string, string | number | boolean> }[]) =>
      api.post<{ added: number }>(
        `/api/admin/studies/${studyId}/dataset/add-bulk`,
        { images },
      ),
    onSuccess: (resp) => {
      toast.success(`Added ${resp.added} image${resp.added !== 1 ? "s" : ""} to study`);
      setSelectedLeft(new Set());
    },
    onError: () => toast.error("Failed to add images"),
    onSettled: invalidateAll,
  });

  // ─── Bulk remove mutation ──────────────────────────────────────────────
  const bulkRemoveMutation = useMutation({
    mutationFn: (ids: number[]) =>
      api.post<{ removed: number }>(
        `/api/admin/studies/${studyId}/dataset/remove`,
        { image_ids: ids },
      ),
    onSuccess: (resp) => {
      toast.success(`Removed ${resp.removed} image${resp.removed !== 1 ? "s" : ""}`);
      setSelectedRight(new Set());
    },
    onError: () => toast.error("Failed to remove images"),
    onSettled: invalidateAll,
  });

  // ─── Click handlers ───────────────────────────────────────────────────
  function handleLeftClick(img: BrowseImage, idx: number, e: React.MouseEvent) {
    if (disabled || img.in_dataset) return;

    if (e.ctrlKey || e.metaKey) {
      setSelectedLeft((prev) => {
        const next = new Set(prev);
        if (next.has(img.image_path)) next.delete(img.image_path);
        else next.add(img.image_path);
        return next;
      });
      lastLeftIdx.current = idx;
      return;
    }

    if (e.shiftKey && lastLeftIdx.current !== null) {
      const start = Math.min(lastLeftIdx.current, idx);
      const end = Math.max(lastLeftIdx.current, idx);
      setSelectedLeft((prev) => {
        const next = new Set(prev);
        for (let i = start; i <= end; i++) {
          const item = leftItems[i];
          if (item && !item.in_dataset) next.add(item.image_path);
        }
        return next;
      });
      return;
    }

    if (selectedLeft.size > 0) {
      setSelectedLeft(new Set());
    }
    lastLeftIdx.current = idx;
    toggleMutation.mutate(img);
  }

  function handleRightClick(img: { id: number; image_path: string }, idx: number, e: React.MouseEvent) {
    if (disabled) return;

    if (e.ctrlKey || e.metaKey) {
      setSelectedRight((prev) => {
        const next = new Set(prev);
        if (next.has(img.id)) next.delete(img.id);
        else next.add(img.id);
        return next;
      });
      lastRightIdx.current = idx;
      return;
    }

    if (e.shiftKey && lastRightIdx.current !== null) {
      const start = Math.min(lastRightIdx.current, idx);
      const end = Math.max(lastRightIdx.current, idx);
      setSelectedRight((prev) => {
        const next = new Set(prev);
        for (let i = start; i <= end; i++) {
          const item = rightItems[i];
          if (item) next.add(item.id);
        }
        return next;
      });
      return;
    }

    if (selectedRight.size > 0) {
      setSelectedRight(new Set());
    }
    lastRightIdx.current = idx;
    bulkRemoveMutation.mutate([img.id]);
  }

  function handleBulkAdd() {
    const images = leftItems
      .filter((img) => selectedLeft.has(img.image_path) && !img.in_dataset)
      .map((img) => ({ image_path: img.image_path, attributes: img.attributes }));
    if (images.length > 0) bulkAddMutation.mutate(images);
  }

  function handleBulkRemove() {
    bulkRemoveMutation.mutate(Array.from(selectedRight));
  }

  // ─── Filter handlers ──────────────────────────────────────────────────
  const toggleFilterValue = useCallback((name: string, val: string) => {
    setFilters((prev) => {
      const cur = prev[name] ?? [];
      const next = cur.includes(val) ? cur.filter((v) => v !== val) : [...cur, val];
      return { ...prev, [name]: next };
    });
    setLeftPage(1);
  }, []);

  const toggleAllFilterValues = useCallback((name: string, all: string[]) => {
    setFilters((prev) => {
      const cur = prev[name] ?? [];
      return { ...prev, [name]: cur.length === all.length ? [] : [...all] };
    });
    setLeftPage(1);
  }, []);

  // ─── DnD handlers ─────────────────────────────────────────────────────
  function handleDragStart(e: DragStartEvent) {
    const img = leftItems.find((i) => i.image_path === e.active.id);
    if (!img) { setDragImage(null); return; }
    // If dragging an unselected item, make it the only selection
    if (!selectedLeft.has(img.image_path)) {
      setSelectedLeft(new Set([img.image_path]));
    }
    setDragImage(img);
  }

  // Count of items being dragged (the dragged item + any other selected)
  const dragCount = dragImage
    ? Math.max(1, selectedLeft.size)
    : 0;

  function handleDragEnd(e: DragEndEvent) {
    if (e.over?.id === "study-drop-zone" && !disabled) {
      // Collect all selected available images for bulk add
      const toAdd = leftItems
        .filter((img) => selectedLeft.has(img.image_path) && !img.in_dataset)
        .map((img) => ({ image_path: img.image_path, attributes: img.attributes }));
      if (toAdd.length > 1) {
        bulkAddMutation.mutate(toAdd);
      } else if (toAdd.length === 1 && dragImage) {
        toggleMutation.mutate(dragImage);
      }
    }
    setDragImage(null);
  }

  // ─── Render ────────────────────────────────────────────────────────────
  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <Card className="overflow-hidden" style={{ height: builderHeight, minHeight: 480, maxHeight: builderHeight }}>
        <div className="grid h-full grid-rows-[minmax(0,1fr)_1px_minmax(0,1fr)]">

          {/* ── Top: Available Images ── */}
          <div className="flex min-h-0 flex-col overflow-hidden">
            {/* Header */}
            <div className="flex-shrink-0 px-4 pt-4 pb-3 space-y-2.5">
              <div className="flex items-center gap-2">
                <h3 className="text-base font-semibold shrink-0">Dataset:</h3>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="h-7 text-xs px-2.5 font-normal" disabled={datasetDisabled}>
                      {datasetName ?? "Select dataset..."}
                      <ChevronDown className="size-3 ml-1.5 opacity-50" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    <DropdownMenuRadioGroup value={datasetName ?? ""} onValueChange={onDatasetChange}>
                      {datasets.map((ds) => (
                        <DropdownMenuRadioItem key={ds.name} value={ds.name}>
                          {ds.name} ({ds.image_count})
                        </DropdownMenuRadioItem>
                      ))}
                    </DropdownMenuRadioGroup>
                  </DropdownMenuContent>
                </DropdownMenu>
                {datasetName && (
                  <span className="text-xs text-muted-foreground shrink-0 ml-auto">
                    {leftTotal} image{leftTotal !== 1 ? "s" : ""}
                  </span>
                )}
              </div>

              {/* Filters */}
              {datasetName && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-sm font-medium shrink-0">Filter:</span>
                {(attrs ?? []).map((attr) => {
                  const allVals = attr.values.map(String);
                  const sel = filters[attr.name] ?? [];
                  const allSel = sel.length === allVals.length;
                  return (
                    <DropdownMenu key={attr.name}>
                      <DropdownMenuTrigger asChild>
                        <Button variant="outline" size="sm" className="h-6 text-[11px] px-2" disabled={disabled}>
                          {attr.name}
                          <Badge variant="secondary" className="ml-1 text-[9px] px-1 py-0">{sel.length}</Badge>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="start" className="max-h-[300px] overflow-y-auto">
                        <DropdownMenuCheckboxItem
                          checked={allSel}
                          onCheckedChange={() => toggleAllFilterValues(attr.name, allVals)}
                          onSelect={(e) => e.preventDefault()}
                        >
                          All
                        </DropdownMenuCheckboxItem>
                        <DropdownMenuSeparator />
                        {allVals.map((v) => (
                          <DropdownMenuCheckboxItem
                            key={v || "__empty__"}
                            checked={sel.includes(v)}
                            onCheckedChange={() => toggleFilterValue(attr.name, v)}
                            onSelect={(e) => e.preventDefault()}
                          >
                            {v || <span className="text-muted-foreground italic">none</span>}
                          </DropdownMenuCheckboxItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  );
                })}
                <Button
                  variant={hideAdded ? "secondary" : "outline"}
                  size="sm"
                  className="h-6 text-[11px] px-2"
                  onClick={() => { setHideAdded(!hideAdded); setLeftPage(1); }}
                  disabled={disabled}
                >
                  {hideAdded ? "Showing unselected" : "Hide added"}
                </Button>
              </div>
              )}

              {/* Bulk add bar */}
              {datasetName && selectedLeft.size > 0 && (
                <div className="flex items-center gap-2 p-2 rounded-md bg-primary/10 border border-primary/20">
                  <span className="text-xs font-medium">{selectedLeft.size} selected</span>
                  <Button
                    size="sm"
                    className="h-6 text-[11px]"
                    onClick={handleBulkAdd}
                    disabled={disabled || bulkAddMutation.isPending}
                  >
                    <Plus className="size-3 mr-1" />
                    Add to Study
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[11px]"
                    onClick={() => setSelectedLeft(new Set())}
                  >
                    Clear
                  </Button>
                </div>
              )}
            </div>

            {/* Scrollable grid */}
            <div
              ref={setLeftGridRef}
              className="flex-1 overflow-y-auto px-4 pb-2 min-h-0 relative"
              onMouseDown={onLeftGridMouseDown}
            >
              {!datasetName && (
                <p className="text-xs text-muted-foreground text-center py-12">
                  Select a dataset to browse available images.
                </p>
              )}
              {datasetName && leftQuery.isLoading && (
                <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(auto-fill, ${leftThumb}px)` }}>
                  {Array.from({ length: 8 }).map((_, i) => (
                    <Skeleton key={i} className="aspect-square rounded-md" />
                  ))}
                </div>
              )}
              {datasetName && leftQuery.isError && (
                <div className="flex items-center gap-2 text-sm text-destructive py-4">
                  <AlertTriangle className="size-4" />
                  Failed to load images.
                </div>
              )}
              {datasetName && !leftQuery.isLoading && leftItems.length > 0 && (
                <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(auto-fill, ${leftThumb}px)` }}>
                  {leftItems.map((img, idx) => (
                    <DraggableImageCard
                      key={img.image_path}
                      image={img}
                      selected={selectedLeft.has(img.image_path)}
                      disabled={disabled}
                      onClick={(e) => handleLeftClick(img, idx, e)}
                    />
                  ))}
                </div>
              )}
              {datasetName && !leftQuery.isLoading && leftItems.length === 0 && !leftQuery.isError && (
                <p className="text-xs text-muted-foreground text-center py-8">
                  No images match the current filters.
                </p>
              )}
              {leftMarqueeRect && <MarqueeOverlay rect={leftMarqueeRect} />}
            </div>

            {/* Footer */}
            {datasetName && (
              <div className="flex-shrink-0 border-t px-4 py-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <PerPageSelect value={leftPerPage} onChange={(v) => { setLeftPerPage(v); setLeftPage(1); }} />
                  <ThumbSizeSlider value={leftThumb} onChange={setLeftThumb} />
                </div>
                <PaginationControls page={leftPage} totalPages={leftTotalPages} onChange={setLeftPage} />
              </div>
            )}
          </div>

          <div className="bg-border" />

          {/* ── Bottom: Study Images ── */}
          <StudyDropZone className="flex min-h-0 flex-col overflow-hidden">
            {/* Header */}
            <div className="flex-shrink-0 px-4 pt-4 pb-3 space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold">Study Images</h3>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-[11px] px-2"
                  onClick={() => setShowDistribution(!showDistribution)}
                >
                  Distribution
                  {showDistribution ? <ChevronUp className="size-3 ml-1" /> : <ChevronDown className="size-3 ml-1" />}
                </Button>
                <span className="text-xs text-muted-foreground">
                  {rightTotal} image{rightTotal !== 1 ? "s" : ""}
                </span>
              </div>

              {showDistribution && (
                <div className="border rounded-md p-3 bg-muted/30">
                  <CompositionChart
                    stats={statsQuery.data}
                    isLoading={statsQuery.isLoading}
                    compact
                  />
                </div>
              )}

              {/* Bulk remove bar */}
              {selectedRight.size > 0 && (
                <div className="flex items-center gap-2 p-2 rounded-md bg-destructive/10 border border-destructive/20">
                  <span className="text-xs font-medium">{selectedRight.size} selected</span>
                  <Button
                    variant="destructive"
                    size="sm"
                    className="h-6 text-[11px]"
                    onClick={handleBulkRemove}
                    disabled={disabled || bulkRemoveMutation.isPending}
                  >
                    <Minus className="size-3 mr-1" />
                    Remove
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[11px]"
                    onClick={() => setSelectedRight(new Set())}
                  >
                    Clear
                  </Button>
                </div>
              )}
            </div>

            {/* Scrollable grid */}
            <div
              ref={setRightGridRef}
              className="flex-1 overflow-y-auto px-4 pb-2 min-h-0 relative"
              onMouseDown={onRightGridMouseDown}
            >
              {rightQuery.isLoading && (
                <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(auto-fill, ${rightThumb}px)` }}>
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="aspect-square rounded-md" />
                  ))}
                </div>
              )}
              {!rightQuery.isLoading && rightItems.length > 0 && (
                <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(auto-fill, ${rightThumb}px)` }}>
                  {rightItems.map((img, idx) => (
                    <button
                      key={img.id}
                      type="button"
                      data-select-id={String(img.id)}
                      onClick={(e) => handleRightClick(img, idx, e)}
                      disabled={disabled}
                      className={cn(
                        "relative rounded-md overflow-hidden group cursor-pointer transition-all",
                        selectedRight.has(img.id)
                          ? "ring-2 ring-destructive ring-offset-1 ring-offset-background"
                          : "ring-1 ring-border hover:ring-destructive/40",
                      )}
                    >
                      <div className="aspect-square bg-muted overflow-hidden">
                        <img
                          src={`/api/admin/images/thumb/${img.image_path}`}
                          alt={img.image_path.split("/").pop() ?? ""}
                          loading="lazy"
                          className="size-full object-contain"
                        />
                      </div>
                      <div className="absolute inset-0 bg-destructive/0 group-hover:bg-destructive/10 transition-colors flex items-center justify-center">
                        <Minus className="size-5 text-destructive opacity-0 group-hover:opacity-80 transition-opacity drop-shadow-sm" />
                      </div>
                      <div className="absolute bottom-0 inset-x-0 bg-foreground/40 backdrop-blur-sm px-1 py-0.5">
                        <div className="text-[9px] font-medium text-white truncate">
                          {img.image_path.split("/").pop()}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
              {!rightQuery.isLoading && rightItems.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <Plus className="size-8 mb-2 opacity-30" />
                  <p className="text-xs">
                    Click or drag images from the dataset to add them to the study.
                  </p>
                </div>
              )}
              {rightMarqueeRect && <MarqueeOverlay rect={rightMarqueeRect} />}
            </div>

            {/* Footer */}
            <div className="flex-shrink-0 border-t px-4 py-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <PerPageSelect value={rightPerPage} onChange={(v) => { setRightPerPage(v); setRightPage(1); }} />
                <ThumbSizeSlider value={rightThumb} onChange={setRightThumb} />
              </div>
              <PaginationControls page={rightPage} totalPages={rightTotalPages} onChange={setRightPage} />
            </div>
          </StudyDropZone>

        </div>
      </Card>

      {/* Drag overlay */}
      <DragOverlay dropAnimation={null}>
        {dragImage && (
          <div className="relative">
            <div
              className="rounded-md overflow-hidden shadow-xl ring-2 ring-primary opacity-90 pointer-events-none"
              style={{ width: leftThumb, height: leftThumb }}
            >
              <img
                src={`/api/admin/images/thumb/${dragImage.image_path}`}
                alt=""
                className="size-full object-contain bg-muted"
              />
            </div>
            {dragCount > 1 && (
              <div className="absolute -top-2 -right-2 bg-primary text-primary-foreground text-xs font-bold rounded-full size-6 flex items-center justify-center shadow-md">
                {dragCount}
              </div>
            )}
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}

// ─── Draggable image card (left panel) ───────────────────────────────────────

interface DraggableImageCardProps {
  image: BrowseImage;
  selected: boolean;
  disabled?: boolean;
  onClick: (e: React.MouseEvent) => void;
}

function DraggableImageCard({ image, selected, disabled, onClick }: DraggableImageCardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: image.image_path,
    disabled: disabled || image.in_dataset,
  });

  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;

  const inStudy = image.in_dataset;
  const fileName = image.image_name || image.image_path.split("/").pop() || "";

  return (
    <div
      ref={setNodeRef}
      style={style}
      data-select-id={inStudy ? undefined : image.image_path}
      {...listeners}
      {...attributes}
      className={cn(
        "relative rounded-md overflow-hidden group transition-all",
        isDragging && "opacity-40",
        inStudy
          ? "opacity-40 cursor-default"
          : "cursor-pointer",
        !inStudy && selected
          ? "ring-2 ring-primary ring-offset-1 ring-offset-background"
          : !inStudy
            ? "ring-1 ring-border hover:ring-primary/40"
            : "ring-1 ring-border/50",
      )}
      onClick={onClick}
    >
      <div className="aspect-square bg-muted overflow-hidden">
        <img
          src={`/api/admin/images/thumb/${image.image_path}`}
          alt={fileName}
          loading="lazy"
          className="size-full object-contain"
        />
      </div>

      {inStudy && (
        <div className="absolute top-1 left-1 h-4 w-4 rounded-full bg-primary flex items-center justify-center shadow-sm">
          <CheckCircle className="h-3 w-3 text-primary-foreground" />
        </div>
      )}

      {!inStudy && !isDragging && (
        <div className="absolute inset-0 bg-primary/0 group-hover:bg-primary/10 transition-colors flex items-center justify-center">
          <Plus className="size-5 text-primary opacity-0 group-hover:opacity-80 transition-opacity drop-shadow-sm" />
        </div>
      )}

      {!inStudy && !isDragging && (
        <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-60 transition-opacity">
          <GripVertical className="size-3.5 text-white drop-shadow-md" />
        </div>
      )}

      {image.missing_file && (
        <div className="absolute top-1 right-1">
          <Badge variant="destructive" className="text-[8px] px-1 py-0">Missing</Badge>
        </div>
      )}

      <div className="absolute bottom-0 inset-x-0 bg-foreground/40 backdrop-blur-sm px-1 py-0.5">
        <div className="text-[9px] font-medium text-white truncate">{fileName}</div>
      </div>
    </div>
  );
}

// ─── Droppable zone wrapper (right panel) ────────────────────────────────────

function StudyDropZone({
  children,
  className,
  style,
}: {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}) {
  const { isOver, setNodeRef } = useDroppable({ id: "study-drop-zone" });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        className,
        "transition-colors duration-200",
        isOver && "bg-primary/5",
      )}
      style={style}
    >
      {children}
    </div>
  );
}

// ─── Shared pagination controls ──────────────────────────────────────────────

function PaginationControls({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (p: number) => void;
}) {
  if (totalPages <= 1) return <div />;
  return (
    <div className="flex items-center gap-1">
      <Button variant="outline" className="h-6 w-6 p-0" onClick={() => onChange(1)} disabled={page <= 1}>
        <ChevronsLeft className="size-3" />
      </Button>
      <Button variant="outline" className="h-6 w-6 p-0" onClick={() => onChange(Math.max(1, page - 1))} disabled={page <= 1}>
        <ChevronLeft className="size-3" />
      </Button>
      <span className="text-[11px] text-muted-foreground px-1.5 tabular-nums">
        {page}/{totalPages}
      </span>
      <Button variant="outline" className="h-6 w-6 p-0" onClick={() => onChange(Math.min(totalPages, page + 1))} disabled={page >= totalPages}>
        <ChevronRight className="size-3" />
      </Button>
      <Button variant="outline" className="h-6 w-6 p-0" onClick={() => onChange(totalPages)} disabled={page >= totalPages}>
        <ChevronsRight className="size-3" />
      </Button>
    </div>
  );
}

function PerPageSelect({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <Select value={String(value)} onValueChange={(v) => onChange(Number(v))}>
      <SelectTrigger className="h-6 text-[11px] w-[65px]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {PAGE_SIZES.map((n) => (
          <SelectItem key={n} value={String(n)}>{n}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function MarqueeOverlay({ rect }: { rect: MarqueeRect }) {
  const style: CSSProperties = {
    position: "absolute",
    left: rect.x,
    top: rect.y,
    width: rect.width,
    height: rect.height,
    pointerEvents: "none",
    zIndex: 50,
  };
  return (
    <div
      style={style}
      className="border-2 border-primary/60 bg-primary/10 rounded-sm"
    />
  );
}

function ThumbSizeSlider({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <Slider
        min={THUMB_MIN}
        max={THUMB_MAX}
        step={THUMB_STEP}
        value={[value]}
        onValueChange={([v]) => onChange(v)}
        className="w-16"
      />
      <span className="text-[10px] text-muted-foreground tabular-nums w-7 text-right">
        {value}
      </span>
    </div>
  );
}
