import { useCallback, useRef, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import type { ImageData } from "@/types";

interface XopatImagePanelProps {
  imageData: ImageData | null;
  loading: boolean;
  shortcutMode?: "none" | "navigation" | "evaluation";
}

function buildViewerUrl(slideId: string) {
  return `/api/xopat/viewer?slides=${encodeURIComponent(slideId)}`;
}

const XOPAT_TUTORIAL_COOKIE =
  "_shadersPin=false; path=/; max-age=31536000; SameSite=Lax";

function disableXopatTutorialCookie() {
  if (typeof document !== "undefined") {
    document.cookie = XOPAT_TUTORIAL_COOKIE;
  }
}

function shouldForwardShortcut(
  event: KeyboardEvent,
  shortcutMode: "none" | "navigation" | "evaluation",
) {
  if (shortcutMode === "none") {
    return false;
  }

  if (event.ctrlKey || event.metaKey || event.altKey) {
    return false;
  }

  const target = event.target as HTMLElement | null;
  if (target) {
    if (target.tagName === "TEXTAREA" || target.tagName === "INPUT") {
      return false;
    }
    if (target.isContentEditable) {
      return false;
    }
  }

  if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    return true;
  }

  if (shortcutMode === "evaluation") {
    return event.key === "Tab" || /^[0-9]$/.test(event.key);
  }

  return false;
}

function installShortcutForwarding(
  frame: HTMLIFrameElement,
  shortcutMode: "none" | "navigation" | "evaluation",
) {
  if (shortcutMode === "none") return;

  const iframeDocument = frame.contentDocument as (Document & {
    __spareEvaluationShortcutsInstalled?: boolean;
  }) | null;

  if (!iframeDocument || iframeDocument.__spareEvaluationShortcutsInstalled) {
    return;
  }

  const swallowShortcut = (event: KeyboardEvent) => {
    if (!shouldForwardShortcut(event, shortcutMode)) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
  };

  const forwardShortcut = (event: KeyboardEvent) => {
    if (!shouldForwardShortcut(event, shortcutMode)) {
      return;
    }

    swallowShortcut(event);

    window.document.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: event.key,
        code: event.code,
        location: event.location,
        repeat: event.repeat,
        shiftKey: event.shiftKey,
        bubbles: true,
        cancelable: true,
      }),
    );
  };

  iframeDocument.addEventListener("keydown", forwardShortcut, true);
  iframeDocument.addEventListener("keyup", swallowShortcut, true);
  iframeDocument.__spareEvaluationShortcutsInstalled = true;
}

function applyEmbeddedViewerMode(
  frame: HTMLIFrameElement | null,
  shortcutMode: "none" | "navigation" | "evaluation",
) {
  if (!frame) return false;

  try {
    const iframeDocument = frame.contentDocument;
    const iframeWindow = frame.contentWindow as
      | (Window & {
          USER_INTERFACE?: {
            MainMenu?: {
              close?: () => void;
              open?: () => void;
              _sync?: () => void;
              context?: { css?: (name: string, value: string) => void };
              content?: { css?: (name: string, value: string) => void };
            };
            Status?: {
              closed?: boolean;
              setClosed?: (closed: boolean) => void;
            };
            Tutorials?: {
              running?: boolean;
              show?: () => void;
              _hideImpl?: (reflectGuiChange: boolean) => void;
            };
            Margins?: { right?: number };
          };
          VIEWER?: unknown;
        })
      | null;

    if (!iframeDocument || !iframeWindow) return false;

    disableXopatTutorialCookie();
    installShortcutForwarding(frame, shortcutMode);

    if (!iframeDocument.getElementById("spare-xopat-embedded-style")) {
      const style = iframeDocument.createElement("style");
      style.id = "spare-xopat-embedded-style";
      style.textContent = `
        #main-panel,
        #main-panel-show,
        #global-help,
        #tutorials-container,
        #viewer-status-bar {
          display: none !important;
        }
      `;
      iframeDocument.head.appendChild(style);
    }

    const userInterface = iframeWindow.USER_INTERFACE;
    const mainMenu = userInterface?.MainMenu;
    const status = userInterface?.Status;
    const tutorials = userInterface?.Tutorials;

    if (!mainMenu || !status || !tutorials) return false;

    tutorials._hideImpl?.(false);
    tutorials.running = false;
    tutorials.show = () => {};
    status.setClosed?.(true);
    status.closed = true;
    iframeDocument.getElementById("viewer-container")?.classList.remove("disabled");

    mainMenu.close?.();
    mainMenu.open = () => {};
    mainMenu.context?.css?.("display", "none");
    mainMenu.content?.css?.("display", "none");

    if (userInterface.Margins) {
      userInterface.Margins.right = 0;
    }
    mainMenu._sync?.();

    return Boolean(iframeWindow.VIEWER);
  } catch {
    return false;
  }
}

function XopatFrame({
  slideId,
  imageData,
  shortcutMode = "none",
}: {
  slideId: string;
  imageData: ImageData;
  shortcutMode?: "none" | "navigation" | "evaluation";
}) {
  const [loaded, setLoaded] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  disableXopatTutorialCookie();

  const handleLoad = useCallback(() => {
    let attempts = 0;

    const finalizeLoad = () => {
      attempts += 1;

      if (
        applyEmbeddedViewerMode(
          iframeRef.current,
          shortcutMode,
        ) ||
        attempts >= 40
      ) {
        setLoaded(true);
        return;
      }

      window.setTimeout(finalizeLoad, 100);
    };

    finalizeLoad();
  }, [shortcutMode]);

  return (
    <>
      <iframe
        ref={iframeRef}
        src={buildViewerUrl(slideId)}
        title={`XOpat viewer for image ${imageData.position}`}
        className="h-full w-full border-0"
        onLoad={handleLoad}
      />
      {!loaded && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-background/70">
          <Skeleton className="aspect-square w-full max-w-lg" />
        </div>
      )}
    </>
  );
}

export function XopatImagePanel({
  imageData,
  loading,
  shortcutMode = "none",
}: XopatImagePanelProps) {
  const slideId = imageData?.xopat_slide_id ?? null;

  if (loading || !imageData) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 bg-secondary/30 p-8">
        <Skeleton className="aspect-square w-full max-w-lg" />
        <Skeleton className="h-4 w-32" />
      </div>
    );
  }

  if (!slideId) {
    return (
      <div className="flex flex-1 flex-col overflow-hidden bg-secondary/30">
        <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">
          XOpat viewer is unavailable for this image.
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden bg-secondary/30">
      <div className="flex flex-1 overflow-hidden p-6">
        <div className="relative flex-1 overflow-hidden rounded-md border border-border/50 bg-background/60">
          <XopatFrame
            key={slideId}
            slideId={slideId}
            imageData={imageData}
            shortcutMode={shortcutMode}
          />
        </div>
      </div>
    </div>
  );
}
