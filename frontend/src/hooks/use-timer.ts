import { useRef, useCallback, useEffect } from "react";
import { api } from "@/api/client";

/**
 * Tracks time spent viewing the current image.
 * - Starts when called with a ratingId
 * - Pauses when the document becomes hidden (visibilitychange)
 * - Saves accumulated time via PUT /api/ratings/:id/time on flush
 */
export function useTimer() {
  const ratingIdRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const accumulatedRef = useRef(0);

  const startTimer = useCallback(() => {
    if (startTimeRef.current === null) {
      startTimeRef.current = Date.now();
    }
  }, []);

  const pauseTimer = useCallback(() => {
    if (startTimeRef.current !== null) {
      accumulatedRef.current += (Date.now() - startTimeRef.current) / 1000;
      startTimeRef.current = null;
    }
  }, []);

  const flush = useCallback(async () => {
    pauseTimer();
    const elapsed = accumulatedRef.current;
    const id = ratingIdRef.current;
    accumulatedRef.current = 0;

    if (id && elapsed > 0) {
      try {
        await api.put(`/api/ratings/${id}/time`, { elapsed });
      } catch {
        // Silently fail - time tracking is best-effort
      }
    }
  }, [pauseTimer]);

  const setRatingId = useCallback(
    (id: number | null) => {
      // Flush any existing timer before switching
      if (ratingIdRef.current !== null && ratingIdRef.current !== id) {
        void flush();
      }
      ratingIdRef.current = id;
      accumulatedRef.current = 0;
      startTimeRef.current = null;
      if (id !== null) {
        startTimer();
      }
    },
    [flush, startTimer],
  );

  // Handle visibility changes
  useEffect(() => {
    function handleVisibility() {
      if (document.hidden) {
        pauseTimer();
      } else if (ratingIdRef.current !== null) {
        startTimer();
      }
    }

    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [pauseTimer, startTimer]);

  // Flush on unmount
  useEffect(() => {
    return () => {
      void flush();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { setRatingId, flush };
}
