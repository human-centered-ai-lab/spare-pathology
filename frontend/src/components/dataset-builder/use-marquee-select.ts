import { useCallback, useRef, useState } from "react";

export interface MarqueeRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface UseMarqueeSelectOptions {
  /** CSS selector for selectable items inside the container */
  itemSelector: string;
  /** Called with the set of data-select-id values that intersect the marquee */
  onSelect: (ids: string[], additive: boolean) => void;
  /** Minimum drag distance before marquee activates */
  threshold?: number;
  disabled?: boolean;
}

/**
 * Hook for rectangle / marquee selection over a scrollable grid container.
 *
 * Returns a ref callback for the container element, a mousedown handler,
 * and the current marquee rect (null when inactive).
 */
export function useMarqueeSelect({
  itemSelector,
  onSelect,
  threshold = 6,
  disabled = false,
}: UseMarqueeSelectOptions) {
  const containerEl = useRef<HTMLDivElement | null>(null);
  const [rect, setRect] = useState<MarqueeRect | null>(null);
  const active = useRef(false);
  const origin = useRef({ x: 0, y: 0 });
  const didActivate = useRef(false);
  const isAdditive = useRef(false);

  // Stable ref callback — safe to use as JSX ref prop
  const setContainerRef = useCallback((node: HTMLDivElement | null) => {
    containerEl.current = node;
  }, []);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (disabled) return;
      if (e.button !== 0) return;
      // Don't start marquee if clicking directly on a selectable item
      const target = e.target as HTMLElement;
      if (target.closest("[data-select-id]")) return;

      const container = containerEl.current;
      if (!container) return;

      const containerRect = container.getBoundingClientRect();
      const x = e.clientX - containerRect.left + container.scrollLeft;
      const y = e.clientY - containerRect.top + container.scrollTop;

      origin.current = { x, y };
      active.current = true;
      didActivate.current = false;
      isAdditive.current = e.ctrlKey || e.metaKey || e.shiftKey;

      let lastEv: MouseEvent | null = null;

      const onMouseMove = (ev: MouseEvent) => {
        lastEv = ev;
        if (!active.current || !container) return;
        const cr = container.getBoundingClientRect();
        const cx = ev.clientX - cr.left + container.scrollLeft;
        const cy = ev.clientY - cr.top + container.scrollTop;

        const dx = cx - origin.current.x;
        const dy = cy - origin.current.y;

        if (!didActivate.current) {
          if (Math.abs(dx) < threshold && Math.abs(dy) < threshold) return;
          didActivate.current = true;
          document.body.style.userSelect = "none";
        }

        const rx = Math.min(origin.current.x, cx);
        const ry = Math.min(origin.current.y, cy);
        setRect({ x: rx, y: ry, width: Math.abs(dx), height: Math.abs(dy) });

        // Auto-scroll when near edges
        const edgeSize = 40;
        const relY = ev.clientY - cr.top;
        if (relY < edgeSize) {
          container.scrollTop -= 8;
        } else if (relY > cr.height - edgeSize) {
          container.scrollTop += 8;
        }
      };

      const onMouseUp = () => {
        active.current = false;
        document.body.style.userSelect = "";
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);

        if (!didActivate.current || !container) {
          // Click on empty space without dragging — clear selection
          if (!isAdditive.current) {
            onSelect([], false);
          }
          setRect(null);
          return;
        }

        // Compute final rect from last known mouse position
        const cr = container.getBoundingClientRect();
        const finalEv = lastEv;
        if (!finalEv) { setRect(null); return; }

        const lx = finalEv.clientX - cr.left + container.scrollLeft;
        const ly = finalEv.clientY - cr.top + container.scrollTop;
        const finalRect = {
          x: Math.min(origin.current.x, lx),
          y: Math.min(origin.current.y, ly),
          width: Math.abs(lx - origin.current.x),
          height: Math.abs(ly - origin.current.y),
        };

        // Find intersecting items
        const items = container.querySelectorAll(itemSelector);
        const ids: string[] = [];

        for (const el of items) {
          const elRect = el.getBoundingClientRect();
          const ex = elRect.left - cr.left + container.scrollLeft;
          const ey = elRect.top - cr.top + container.scrollTop;

          if (
            finalRect.x < ex + elRect.width &&
            finalRect.x + finalRect.width > ex &&
            finalRect.y < ey + elRect.height &&
            finalRect.y + finalRect.height > ey
          ) {
            const id = (el as HTMLElement).dataset.selectId;
            if (id) ids.push(id);
          }
        }

        onSelect(ids, isAdditive.current);

        setRect(null);
      };

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    [disabled, itemSelector, onSelect, threshold],
  );

  return { setContainerRef, onMouseDown, rect };
}
