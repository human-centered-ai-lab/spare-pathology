import { useAuth } from "@/hooks/use-auth";
import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { toast } from "sonner";
import { useTimer } from "@/hooks/use-timer";
import type {
  ParticipantStudy,
  ImageListItem,
  ImageData,
  Rating,
  RatingSchema,
  CompletionStatus,
} from "@/types";

type RatingResponseValue = number | string | string[] | null;
type SaveKind = "response" | "text-response" | "uncertainty" | "failure-reason";

interface QueuedSave {
  key: string;
  kind: SaveKind;
  ratingId: number;
  position: number;
  value: RatingResponseValue | boolean;
  questionId?: string;
  version: number;
  updatedAt: number;
  errorMessage?: string;
}

interface SaveSnapshot {
  pendingCount: number;
  errorCount: number;
  isSaving: boolean;
  isFlushing: boolean;
  lastError: string | null;
}

const MAX_SAVE_ATTEMPTS = 4;
const TEXT_SAVE_DEBOUNCE_MS = 500;
const SAVE_RETRY_DELAYS_MS = [500, 1000, 2000];

const EMPTY_SAVE_SNAPSHOT: SaveSnapshot = {
  pendingCount: 0,
  errorCount: 0,
  isSaving: false,
  isFlushing: false,
  lastError: null,
};

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function saveStorageKey(studyId: number, userId: number) {
  return `spare.pendingRatingSaves.${userId}.${studyId}`;
}

function legacySaveStorageKey(studyId: number, userId: number) {
  return `syneval.pendingRatingSaves.${userId}.${studyId}`;
}

function saveKey(kind: SaveKind, ratingId: number, questionId?: string) {
  return `${kind}:${ratingId}:${questionId ?? "_"}`;
}

function normalizeError(err: unknown) {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Network error while saving.";
}

function shouldRetrySave(err: unknown) {
  return !(err instanceof ApiError) || err.status >= 500;
}

function hasOwn(obj: object, key: string) {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

function hasReadySave(
  queuedSaves: Map<string, QueuedSave>,
  debounceTimers: Map<string, ReturnType<typeof window.setTimeout>>,
) {
  return Array.from(queuedSaves.values()).some(
    (save) => !debounceTimers.has(save.key),
  );
}

function applySaveToResponses(
  responses: Record<string, RatingResponseValue>,
  save: QueuedSave,
  serverResponses?: Record<string, RatingResponseValue>,
) {
  const next = { ...responses };

  if ((save.kind === "response" || save.kind === "text-response") && save.questionId) {
    next[save.questionId] = (serverResponses?.[save.questionId] ?? save.value) as RatingResponseValue;
  }

  if (save.kind === "failure-reason") {
    if (serverResponses && hasOwn(serverResponses, "failure_reason")) {
      next.failure_reason = serverResponses.failure_reason;
    } else if (save.value === null) {
      delete next.failure_reason;
    } else {
      next.failure_reason = save.value as RatingResponseValue;
    }
  }

  return next;
}

function statusForResponses(
  responses: Record<string, RatingResponseValue> | null | undefined,
  schema: RatingSchema | null | undefined,
  hasRating: boolean,
): ImageListItem["status"] {
  if (!hasRating) return "not_opened";

  const ordinalIds = (schema?.questions ?? [])
    .filter((question) => question.type === "ordinal")
    .map((question) => question.id);

  if (ordinalIds.length === 0) return "complete";
  if (!responses) return "opened";

  const answered = ordinalIds.filter((questionId) => {
    const value = responses[questionId];
    return value !== null && value !== undefined;
  }).length;

  if (answered === 0) return "opened";
  if (answered < ordinalIds.length) return "partial";
  return "complete";
}

function isQueuedSave(value: unknown): value is QueuedSave {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<QueuedSave>;
  return (
    typeof candidate.key === "string" &&
    typeof candidate.kind === "string" &&
    typeof candidate.ratingId === "number" &&
    typeof candidate.position === "number" &&
    typeof candidate.version === "number"
  );
}

export function useEvaluation(studyId: number, isImpersonating = false) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const userId = user?.id ?? 0;
  const { setRatingId, flush: flushTimer } = useTimer();

  const [manualPositions, setManualPositions] = useState<Record<number, number>>({});
  const [focusedQuestionIndex, setFocusedQuestionIndex] = useState(0);
  const [saveSnapshot, setSaveSnapshot] = useState<SaveSnapshot>(EMPTY_SAVE_SNAPSHOT);

  const queuedSavesRef = useRef<Map<string, QueuedSave>>(new Map());
  const failedSavesRef = useRef<Map<string, QueuedSave>>(new Map());
  const persistedSavesRef = useRef<Map<string, QueuedSave>>(new Map());
  const activeSaveRef = useRef<QueuedSave | null>(null);
  const saveVersionsRef = useRef<Map<string, number>>(new Map());
  const debounceTimersRef = useRef<Map<string, ReturnType<typeof window.setTimeout>>>(new Map());
  const processingPromiseRef = useRef<Promise<void> | null>(null);
  const isFlushingRef = useRef(false);
  const ensureProcessingRef = useRef<() => Promise<void>>(async () => {});

  const persistSaves = useCallback(() => {
    if (typeof window === "undefined") return;

    const entries = Array.from(persistedSavesRef.current.values());
    if (entries.length === 0) {
      window.localStorage.removeItem(saveStorageKey(studyId, userId));
      return;
    }

    window.localStorage.setItem(saveStorageKey(studyId, userId), JSON.stringify(entries));
  }, [studyId, userId]);

  const refreshSaveSnapshot = useCallback(() => {
    const active = activeSaveRef.current;
    const pendingKeys = new Set(persistedSavesRef.current.keys());
    if (active) pendingKeys.add(active.key);

    const firstError = failedSavesRef.current.values().next().value?.errorMessage ?? null;
    setSaveSnapshot({
      pendingCount: pendingKeys.size,
      errorCount: failedSavesRef.current.size,
      isSaving: Boolean(active || queuedSavesRef.current.size > 0 || debounceTimersRef.current.size > 0),
      isFlushing: isFlushingRef.current,
      lastError: firstError,
    });
  }, []);

  // ─── Fetch study project info ────────────────────────────────────────────────
  const studiesQuery = useQuery<ParticipantStudy[]>({
    queryKey: ["studies"],
    queryFn: () => api.get<ParticipantStudy[]>("/api/studies"),
    staleTime: 5 * 60 * 1000,
  });

  const studyProject = useMemo(() => {
    if (!studiesQuery.data) return null;
    return studiesQuery.data.find((s) => s.id === studyId) ?? null;
  }, [studiesQuery.data, studyId]);
  const currentPosition =
    manualPositions[studyId] ?? studyProject?.last_viewed_position ?? 1;

  // ─── Fetch image list ────────────────────────────────────────────────────────
  const imageListQuery = useQuery<ImageListItem[]>({
    queryKey: ["studies", studyId, "images"],
    queryFn: () =>
      api.get<ImageListItem[]>(`/api/studies/${studyId}/images`),
    enabled: !!studyId,
  });

  const imageList = imageListQuery.data ?? [];

  // ─── Fetch current image data ────────────────────────────────────────────────
  // Fire in parallel with imageList (don't wait for it). Once imageList
  // finishes and is empty, disable to avoid 404s on empty projects.
  const imageDataQuery = useQuery<ImageData>({
    queryKey: ["studies", studyId, "image", currentPosition],
    queryFn: () =>
      api.get<ImageData>(
        `/api/studies/${studyId}/image/${currentPosition}`,
      ),
    enabled:
      !!studyId &&
      !!studyProject &&
      currentPosition >= 1 &&
      (!imageListQuery.isFetched || imageList.length > 0),
    retry: false,
  });

  const currentImageData = imageDataQuery.data ?? null;
  const currentRating = (currentImageData?.rating as Rating | null) ?? null;
  const currentRatingId = currentRating?.id ?? null;

  const updateImageListStatus = useCallback(
    (
      position: number,
      responses: Record<string, RatingResponseValue> | null | undefined,
      hasRating: boolean,
    ) => {
      const nextStatus = statusForResponses(responses, studyProject?.rating_schema, hasRating);
      queryClient.setQueryData<ImageListItem[]>(
        ["studies", studyId, "images"],
        (old) => {
          if (!old) return old;
          return old.map((item) =>
            item.position === position
              ? { ...item, status: nextStatus }
              : item,
          );
        },
      );
    },
    [queryClient, studyId, studyProject?.rating_schema],
  );

  const mergeSaveIntoImageData = useCallback(
    (save: QueuedSave, serverRating?: Rating) => {
      let nextResponsesForStatus: Record<string, RatingResponseValue> | null = null;

      queryClient.setQueryData<ImageData>(
        ["studies", studyId, "image", save.position],
        (old) => {
          if (!old || !old.rating) return old;

          const baseResponses = (old.rating.responses ?? {}) as Record<string, RatingResponseValue>;
          const serverResponses = serverRating?.responses as
            | Record<string, RatingResponseValue>
            | undefined;
          const nextResponses =
            save.kind === "uncertainty"
              ? baseResponses
              : applySaveToResponses(baseResponses, save, serverResponses);

          nextResponsesForStatus = nextResponses;

          return {
            ...old,
            rating: {
              ...old.rating,
              ...(serverRating ?? {}),
              responses: nextResponses,
              uncertainty:
                save.kind === "uncertainty"
                  ? serverRating?.uncertainty ?? Boolean(save.value)
                  : serverRating?.uncertainty ?? old.rating.uncertainty,
            } as Rating,
          };
        },
      );

      if (nextResponsesForStatus) {
        updateImageListStatus(save.position, nextResponsesForStatus, true);
      }
    },
    [queryClient, studyId, updateImageListStatus],
  );

  const sendQueuedSave = useCallback((save: QueuedSave) => {
    if (save.kind === "response") {
      return api.put<Rating>(`/api/ratings/${save.ratingId}/response`, {
        question_id: save.questionId,
        value: save.value,
      });
    }

    if (save.kind === "text-response") {
      return api.put<Rating>(`/api/ratings/${save.ratingId}/text-response`, {
        question_id: save.questionId,
        value: save.value,
      });
    }

    if (save.kind === "uncertainty") {
      return api.put<Rating>(`/api/ratings/${save.ratingId}/uncertainty`, {
        value: save.value,
      });
    }

    return api.put<Rating>(`/api/ratings/${save.ratingId}/failure-reason`, {
      value: save.value,
    });
  }, []);

  const runSaveQueue = useCallback(async () => {
    while (queuedSavesRef.current.size > 0) {
      const save = Array.from(queuedSavesRef.current.values())
        .find((entry) => !debounceTimersRef.current.has(entry.key));

      if (!save) break;

      queuedSavesRef.current.delete(save.key);
      failedSavesRef.current.delete(save.key);

      const currentVersion = saveVersionsRef.current.get(save.key);
      if (currentVersion !== save.version) {
        continue;
      }

      activeSaveRef.current = save;
      refreshSaveSnapshot();

      let saved = false;
      let lastError = "Failed to save rating.";

      for (let attempt = 0; attempt < MAX_SAVE_ATTEMPTS; attempt += 1) {
        if (saveVersionsRef.current.get(save.key) !== save.version) {
          saved = true;
          break;
        }

        try {
          const data = await sendQueuedSave(save);

          if (saveVersionsRef.current.get(save.key) === save.version) {
            persistedSavesRef.current.delete(save.key);
            failedSavesRef.current.delete(save.key);
            mergeSaveIntoImageData(save, data);
            persistSaves();
            refreshSaveSnapshot();
          }

          saved = true;
          break;
        } catch (err) {
          lastError = normalizeError(err);

          if (saveVersionsRef.current.get(save.key) !== save.version) {
            saved = true;
            break;
          }

          if (attempt < MAX_SAVE_ATTEMPTS - 1 && shouldRetrySave(err)) {
            const retrySave = {
              ...save,
              errorMessage: `Retrying save: ${lastError}`,
            };
            persistedSavesRef.current.set(save.key, retrySave);
            persistSaves();
            refreshSaveSnapshot();
            await delay(SAVE_RETRY_DELAYS_MS[Math.min(attempt, SAVE_RETRY_DELAYS_MS.length - 1)]);
            continue;
          }

          break;
        }
      }

      if (!saved && saveVersionsRef.current.get(save.key) === save.version) {
        const failedSave = { ...save, errorMessage: lastError };
        failedSavesRef.current.set(save.key, failedSave);
        persistedSavesRef.current.set(save.key, failedSave);
        persistSaves();
        toast.error(`Failed to save rating: ${lastError}`);
      }

      activeSaveRef.current = null;
      refreshSaveSnapshot();
    }
  }, [
    mergeSaveIntoImageData,
    persistSaves,
    refreshSaveSnapshot,
    sendQueuedSave,
  ]);

  const ensureProcessing = useCallback(() => {
    if (processingPromiseRef.current) {
      return processingPromiseRef.current;
    }

    const promise = runSaveQueue().finally(() => {
      processingPromiseRef.current = null;
      if (hasReadySave(queuedSavesRef.current, debounceTimersRef.current)) {
        void ensureProcessingRef.current();
      }
      refreshSaveSnapshot();
    });

    processingPromiseRef.current = promise;
    return promise;
  }, [refreshSaveSnapshot, runSaveQueue]);

  useEffect(() => {
    ensureProcessingRef.current = ensureProcessing;
  }, [ensureProcessing]);

  const flushPendingSaves = useCallback(async () => {
    isFlushingRef.current = true;
    refreshSaveSnapshot();

    try {
      debounceTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      debounceTimersRef.current.clear();

      failedSavesRef.current.forEach((save, key) => {
        queuedSavesRef.current.set(key, { ...save, errorMessage: undefined });
      });
      failedSavesRef.current.clear();
      refreshSaveSnapshot();

      while (
        queuedSavesRef.current.size > 0 ||
        activeSaveRef.current ||
        processingPromiseRef.current
      ) {
        await ensureProcessing();
      }

      if (failedSavesRef.current.size > 0) {
        const error = failedSavesRef.current.values().next().value?.errorMessage;
        throw new Error(error ?? "A rating save is still failing.");
      }
    } finally {
      isFlushingRef.current = false;
      refreshSaveSnapshot();
    }
  }, [ensureProcessing, refreshSaveSnapshot]);

  const enqueueSave = useCallback(
    (
      kind: SaveKind,
      value: RatingResponseValue | boolean,
      questionId?: string,
      debounceMs = 0,
    ) => {
      if (!currentRatingId) {
        toast.error("The rating is still being prepared. Try again in a moment.");
        return;
      }

      const key = saveKey(kind, currentRatingId, questionId);
      const version = (saveVersionsRef.current.get(key) ?? 0) + 1;
      saveVersionsRef.current.set(key, version);

      const save: QueuedSave = {
        key,
        kind,
        ratingId: currentRatingId,
        position: currentPosition,
        questionId,
        value,
        version,
        updatedAt: Date.now(),
      };

      failedSavesRef.current.delete(key);
      queuedSavesRef.current.set(key, save);
      persistedSavesRef.current.set(key, save);
      persistSaves();
      mergeSaveIntoImageData(save);

      const existingTimer = debounceTimersRef.current.get(key);
      if (existingTimer) {
        window.clearTimeout(existingTimer);
        debounceTimersRef.current.delete(key);
      }

      if (debounceMs > 0) {
        const timer = window.setTimeout(() => {
          debounceTimersRef.current.delete(key);
          refreshSaveSnapshot();
          void ensureProcessing();
        }, debounceMs);
        debounceTimersRef.current.set(key, timer);
      } else {
        void ensureProcessing();
      }

      refreshSaveSnapshot();
    },
    [
      currentPosition,
      currentRatingId,
      ensureProcessing,
      mergeSaveIntoImageData,
      persistSaves,
      refreshSaveSnapshot,
    ],
  );

  // Restore queued saves after reload so an interrupted tab does not silently
  // discard a rating change that was already shown optimistically.
  useEffect(() => {
    queuedSavesRef.current.clear();
    failedSavesRef.current.clear();
    persistedSavesRef.current.clear();
    activeSaveRef.current = null;
    saveVersionsRef.current.clear();
    debounceTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    debounceTimersRef.current.clear();

    if (isImpersonating || !userId) return;

    const legacyKey = legacySaveStorageKey(studyId, userId);
    for (const storageKey of [legacyKey, saveStorageKey(studyId, userId)]) {
      const raw = window.localStorage.getItem(storageKey);
      if (!raw) continue;
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          for (const item of parsed) {
            if (!isQueuedSave(item)) continue;
            const existing = persistedSavesRef.current.get(item.key);
            if (existing && (existing.updatedAt ?? 0) > (item.updatedAt ?? 0)) continue;
            const save = { ...item, errorMessage: undefined };
            persistedSavesRef.current.set(save.key, save);
            queuedSavesRef.current.set(save.key, save);
            saveVersionsRef.current.set(save.key, save.version);
          }
        }
      } catch {
        window.localStorage.removeItem(storageKey);
      }
    }

    // Persist the merged queue before removing its previous storage key.
    persistSaves();
    window.localStorage.removeItem(legacyKey);
    refreshSaveSnapshot();

    if (queuedSavesRef.current.size > 0) {
      void ensureProcessingRef.current();
    }

    const debounceTimers = debounceTimersRef.current;
    return () => {
      debounceTimers.forEach((timer) => window.clearTimeout(timer));
      debounceTimers.clear();
    };
  }, [persistSaves, refreshSaveSnapshot, studyId, userId, isImpersonating]);

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (persistedSavesRef.current.size === 0) return;
      event.preventDefault();
      event.returnValue = "";
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);

  useEffect(() => {
    if (!currentImageData?.rating) return;
    updateImageListStatus(
      currentPosition,
      currentImageData.rating.responses as Record<string, RatingResponseValue>,
      true,
    );
  }, [
    currentImageData?.dataset_image_id,
    currentImageData?.rating,
    currentPosition,
    updateImageListStatus,
  ]);

  // ─── Timer management ────────────────────────────────────────────────────────
  useEffect(() => {
    if (currentRatingId && !studyProject?.submitted && !isImpersonating) {
      setRatingId(currentRatingId);
    } else {
      setRatingId(null);
    }
  }, [currentRatingId, setRatingId, studyProject?.submitted, isImpersonating]);

  // ─── Navigation ──────────────────────────────────────────────────────────────
  const goToImage = useCallback(
    async (position: number) => {
      if (position < 1 || (imageList.length > 0 && position > imageList.length))
        return;
      if (position === currentPosition) return;

      try {
        await flushTimer();
        await flushPendingSaves();
      } catch {
        toast.error("Could not switch images because the latest rating has not been saved.");
        return;
      }

      setManualPositions((prev) => ({
        ...prev,
        [studyId]: position,
      }));
      setFocusedQuestionIndex(0);
    },
    [currentPosition, flushPendingSaves, imageList.length, flushTimer, studyId],
  );

  const goNext = useCallback(async () => {
    const max = imageList.length || currentImageData?.total_images || 0;
    if (currentPosition < max) {
      await goToImage(currentPosition + 1);
    }
  }, [currentPosition, imageList.length, currentImageData?.total_images, goToImage]);

  const goPrev = useCallback(async () => {
    if (currentPosition > 1) {
      await goToImage(currentPosition - 1);
    }
  }, [currentPosition, goToImage]);

  // ─── Save actions ────────────────────────────────────────────────────────────
  const saveResponse = useCallback(
    (questionId: string, value: number) => {
      enqueueSave("response", value, questionId);
    },
    [enqueueSave],
  );

  const saveTextResponse = useCallback(
    (questionId: string, value: string) => {
      enqueueSave("text-response", value, questionId, TEXT_SAVE_DEBOUNCE_MS);
    },
    [enqueueSave],
  );

  const saveUncertainty = useCallback(
    (value: boolean) => {
      enqueueSave("uncertainty", value);
    },
    [enqueueSave],
  );

  const saveFailureReason = useCallback(
    (value: string | string[] | null) => {
      enqueueSave("failure-reason", value);
    },
    [enqueueSave],
  );

  // ─── Submit flow ─────────────────────────────────────────────────────────────
  const checkCompletion = useCallback(async () => {
    await flushPendingSaves();
    const result = await queryClient.fetchQuery<CompletionStatus>({
      queryKey: ["studies", studyId, "completion"],
      queryFn: () =>
        api.get<CompletionStatus>(
          `/api/studies/${studyId}/completion-status`,
        ),
    });
    return result;
  }, [flushPendingSaves, studyId, queryClient]);

  const submitMutation = useMutation({
    mutationFn: () =>
      api.post<{ ok: boolean; submitted_at: string }>(
        `/api/studies/${studyId}/submit`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["studies"] });
      void queryClient.invalidateQueries({
        queryKey: ["studies", studyId, "images"],
      });
    },
  });

  const submit = useCallback(async () => {
    await flushTimer();
    await flushPendingSaves();
    return submitMutation.mutateAsync();
  }, [flushPendingSaves, submitMutation, flushTimer]);

  // ─── Read-only state ─────────────────────────────────────────────────────────
  const isSubmitted = studyProject?.submitted ?? false;
  const isReadOnly = isSubmitted || isImpersonating || (
    !user?.is_test_user && studyProject?.status !== "active"
  );

  // ─── Focus management ────────────────────────────────────────────────────────
  const advanceFocus = useCallback(() => {
    const questions = studyProject?.rating_schema?.questions ?? [];
    setFocusedQuestionIndex((prev) =>
      prev < questions.length - 1 ? prev + 1 : prev,
    );
  }, [studyProject?.rating_schema?.questions]);

  return {
    // Study data
    studyProject,
    studyLoading: studiesQuery.isLoading,

    // Image list
    imageList,
    imageListLoading: imageListQuery.isLoading,

    // Current image
    currentPosition,
    currentImageData,
    currentRating,
    currentRatingId,
    imageDataLoading: !studyProject || imageDataQuery.isLoading,

    // Navigation
    goToImage,
    goNext,
    goPrev,

    // Rating actions
    saveResponse,
    saveTextResponse,
    saveUncertainty,
    saveFailureReason,

    // Save state
    saveStatus: saveSnapshot,
    flushPendingSaves,

    // Focus
    focusedQuestionIndex,
    setFocusedQuestionIndex,
    advanceFocus,

    // Submit
    checkCompletion,
    submit,
    submitPending: submitMutation.isPending,

    // State
    isSubmitted,
    isReadOnly,

    // Timer
    flushTimer,
  };
}
