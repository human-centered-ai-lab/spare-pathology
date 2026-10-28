import { useEffect } from "react";

interface UseKeyboardShortcutsOptions {
  onPrev: () => void;
  onNext: () => void;
  onScore: (score: number) => void;
  onAdvanceFocus: () => void;
  enabled: boolean;
  maxScore: number;
}

/**
 * Keyboard shortcuts for the evaluation interface:
 * - ArrowLeft: previous image
 * - ArrowRight: next image
 * - 1-9: quick-select ordinal score on focused question
 * - Tab: advance focused question (prevented default)
 */
export function useKeyboardShortcuts({
  onPrev,
  onNext,
  onScore,
  onAdvanceFocus,
  enabled,
  maxScore,
}: UseKeyboardShortcutsOptions) {
  useEffect(() => {
    if (!enabled) return;

    function handleKeyDown(e: KeyboardEvent) {
      // Ignore if the user is typing in a textarea, input, or contentEditable
      const el = e.target as HTMLElement;
      if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") return;
      if (el.isContentEditable) return;

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        onPrev();
        return;
      }

      if (e.key === "ArrowRight") {
        e.preventDefault();
        onNext();
        return;
      }

      if (e.key === "Tab") {
        e.preventDefault();
        onAdvanceFocus();
        return;
      }

      // Number keys 0-9
      const num = parseInt(e.key, 10);
      if (!isNaN(num) && num >= 0 && num <= maxScore) {
        e.preventDefault();
        onScore(num);
        return;
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [enabled, onPrev, onNext, onScore, onAdvanceFocus, maxScore]);
}
