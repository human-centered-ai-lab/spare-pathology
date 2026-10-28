import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowUpDown, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ImageListItem } from "@/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";

interface ImageSidebarProps {
  images: ImageListItem[];
  currentPosition: number;
  onSelect: (position: number) => void;
  loading: boolean;
  attributeColumns?: string[];
  imageColumnLabel?: string;
  getImageLabel?: (image: ImageListItem) => string;
  showStatusIndicator?: boolean;
  imageColumnSort?: "position" | "label";
  className?: string;
  tableClassName?: string;
}

type SortDirection = "asc" | "desc";

const IMAGE_POSITION_SORT_KEY = "__image_position__";

const collator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base",
});

function formatAttributeHeader(name: string) {
  if (!name) return name;
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatAttributeValue(value: string | number | boolean) {
  if (typeof value === "string") {
    return value.replace(/_/g, " ");
  }
  return String(value);
}

export function ImageSidebar({
  images,
  currentPosition,
  onSelect,
  loading,
  attributeColumns: attributeColumnsProp,
  imageColumnLabel = "Image",
  getImageLabel = (image) => `Image ${image.position}`,
  showStatusIndicator = true,
  imageColumnSort = "position",
  className,
  tableClassName,
}: ImageSidebarProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const handleClick = useCallback(
    (position: number) => {
      void onSelect(position);
    },
    [onSelect],
  );

  const attributeColumns = useMemo(() => {
    if (attributeColumnsProp && attributeColumnsProp.length > 0) {
      return attributeColumnsProp;
    }

    const seen = new Set<string>();
    const names: string[] = [];

    for (const img of images) {
      for (const name of Object.keys(img.visible_attributes ?? {})) {
        if (seen.has(name)) continue;
        seen.add(name);
        names.push(name);
      }
    }

    return names;
  }, [attributeColumnsProp, images]);

  const sortedImages = useMemo(() => {
    if (!sortKey) return images;

    const sorted = [...images];
    sorted.sort((a, b) => {
      if (sortKey === IMAGE_POSITION_SORT_KEY) {
        const comparison = imageColumnSort === "label"
          ? collator.compare(getImageLabel(a), getImageLabel(b))
          : a.position - b.position;
        return sortDirection === "asc" ? comparison : -comparison;
      }

      const aValue = a.visible_attributes?.[sortKey];
      const bValue = b.visible_attributes?.[sortKey];

      const aMissing = aValue === null || aValue === undefined;
      const bMissing = bValue === null || bValue === undefined;

      let comparison = 0;
      if (aMissing && bMissing) {
        comparison = 0;
      } else if (aMissing) {
        comparison = 1;
      } else if (bMissing) {
        comparison = -1;
      } else if (typeof aValue === "number" && typeof bValue === "number") {
        comparison = aValue - bValue;
      } else if (typeof aValue === "boolean" && typeof bValue === "boolean") {
        comparison = Number(aValue) - Number(bValue);
      } else {
        comparison = collator.compare(String(aValue), String(bValue));
      }

      if (comparison === 0) {
        comparison = a.position - b.position;
      }

      return sortDirection === "asc" ? comparison : -comparison;
    });

    return sorted;
  }, [getImageLabel, imageColumnSort, images, sortDirection, sortKey]);

  const handleSort = useCallback((columnKey: string) => {
    setSortKey((prevKey) => {
      if (prevKey !== columnKey) {
        setSortDirection("asc");
        return columnKey;
      }

      if (sortDirection === "asc") {
        setSortDirection("desc");
        return columnKey;
      }

      setSortDirection("asc");
      return null;
    });
  }, [sortDirection]);

  const handleRowKeyDown = useCallback((event: React.KeyboardEvent, position: number) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    void onSelect(position);
  }, [onSelect]);

  useLayoutEffect(() => {
    const viewport = viewportRef.current?.querySelector<HTMLElement>(
      '[data-slot="scroll-area-viewport"]',
    );
    const item = viewport?.querySelector<HTMLElement>(
      `[data-image-position="${currentPosition}"]`,
    );

    if (!viewport || !item) return;

    const viewportRect = viewport.getBoundingClientRect();
    const itemRect = item.getBoundingClientRect();
    const padding = 12;

    if (itemRect.top < viewportRect.top + padding) {
      viewport.scrollTop -= viewportRect.top + padding - itemRect.top;
    } else if (itemRect.bottom > viewportRect.bottom - padding) {
      viewport.scrollTop += itemRect.bottom - (viewportRect.bottom - padding);
    }
  }, [currentPosition, sortedImages]);

  const renderSortIcon = useCallback((columnKey: string) => {
    if (sortKey !== columnKey) {
      return <ArrowUpDown className="size-3.5 text-muted-foreground/70" />;
    }

    return sortDirection === "asc"
      ? <ChevronUp className="size-3.5 text-foreground" />
      : <ChevronDown className="size-3.5 text-foreground" />;
  }, [sortDirection, sortKey]);

  if (loading) {
    return (
      <div
        ref={viewportRef}
        data-image-sidebar="true"
        className={cn(
          "h-full w-[20.4rem] min-w-[15.3rem] max-w-[42.5vw] border-r border-border bg-card",
          className,
        )}
      >
        <ScrollArea className="h-full min-h-0">
          <div className="p-3">
            <div className="space-y-0.5">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-9 animate-pulse rounded-md bg-muted" />
              ))}
            </div>
          </div>
        </ScrollArea>
      </div>
    );
  }

  return (
    <div
      ref={viewportRef}
      data-image-sidebar="true"
      className={cn(
        "flex h-full min-h-0 w-[20.4rem] min-w-[15.3rem] max-w-[42.5vw] flex-col overflow-hidden border-r border-border bg-card",
        className,
      )}
    >
      <ScrollArea className="min-h-0 min-w-0 flex-1" scrollbars="both">
        <Table
          containerClassName="min-w-full w-max overflow-visible"
          className={cn("min-w-full w-max text-xs", tableClassName)}
        >
          <TableHeader className="sticky top-0 z-10 bg-card">
            <TableRow>
              <TableHead className="w-px whitespace-nowrap">
                <button
                  type="button"
                  className="flex items-center gap-1 font-medium"
                  onClick={() => handleSort(IMAGE_POSITION_SORT_KEY)}
                >
                  <span>{imageColumnLabel}</span>
                  {renderSortIcon(IMAGE_POSITION_SORT_KEY)}
                </button>
              </TableHead>
              {attributeColumns.map((attributeName) => (
                <TableHead key={attributeName}>
                  <button
                  type="button"
                  className="flex items-center gap-1 font-medium"
                  onClick={() => handleSort(attributeName)}
                >
                  <span>{formatAttributeHeader(attributeName)}</span>
                  {renderSortIcon(attributeName)}
                </button>
              </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody className="[&_tr]:border-0">
            {sortedImages.map((img) => (
              <TableRow
                key={img.dataset_image_id}
                data-image-position={img.position}
                data-state={img.position === currentPosition ? "selected" : undefined}
                aria-selected={img.position === currentPosition}
                tabIndex={0}
                onClick={() => handleClick(img.position)}
                onKeyDown={(event) => handleRowKeyDown(event, img.position)}
                className={cn(
                  "cursor-pointer data-[state=selected]:bg-primary/5 hover:data-[state=selected]:bg-primary/5",
                  img.position === currentPosition
                    ? "font-medium text-foreground"
                    : "text-muted-foreground",
                )}
              >
                <TableCell className="w-px whitespace-nowrap">
                  <div className="flex items-center gap-2">
                    {showStatusIndicator && (
                      <span
                        className={cn(
                          "h-1.5 w-1.5 shrink-0 rounded-full",
                          img.status === "complete"
                            ? "bg-success"
                            : img.status === "partial"
                              ? "bg-warning"
                              : "bg-muted-foreground/30",
                        )}
                      />
                    )}
                    <span
                      className="block max-w-[14rem] truncate"
                      title={getImageLabel(img)}
                    >
                      {getImageLabel(img)}
                    </span>
                  </div>
                </TableCell>
                {attributeColumns.map((attributeName) => (
                  <TableCell key={attributeName}>
                    {img.visible_attributes?.[attributeName] !== undefined ? (
                      <span
                        className="block max-w-[14rem] truncate"
                        title={formatAttributeValue(img.visible_attributes[attributeName])}
                      >
                        {formatAttributeValue(img.visible_attributes[attributeName])}
                      </span>
                    ) : ""}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  );
}
