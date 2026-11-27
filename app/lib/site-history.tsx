import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigationType } from "react-router";

type BrowserNavigation = EventTarget & {
  readonly currentEntry: { index: number } | null;
  readonly canGoBack: boolean;
  entries(): readonly { url: string | null }[];
};

function browserNavigation(): BrowserNavigation | undefined {
  return (window as Window & { navigation?: BrowserNavigation }).navigation;
}

function isSitePage(url: string | null | undefined): boolean {
  if (!url) return false;
  try {
    const candidate = new URL(url);
    const base = import.meta.env.BASE_URL;
    if (
      candidate.origin !== window.location.origin ||
      !candidate.pathname.startsWith(base)
    )
      return false;
    const path = candidate.pathname
      .slice(base.length)
      .replace(/^\/+|\/+$/g, "")
      .replace(/^(en|zh)(?:\/|$)/, "");
    return /^(?:|releases(?:\/[^/]+)?|master(?:\/\d+)?|build\/[^/]+|guide|integration|packages|licenses|reference|self-build|history)$/.test(
      path,
    );
  } catch {
    return false;
  }
}

// The Navigation API exposes only accessible, contiguous same-origin history.
// Never infer a previous page from history.length or document.referrer.
function nativeCanGoBack(nav: BrowserNavigation): boolean {
  const index = nav.currentEntry?.index ?? -1;
  return (
    nav.canGoBack && index > 0 && isSitePage(nav.entries()[index - 1]?.url)
  );
}

type KnownEntry = { index: number; key: string };
const HistoryContext = createContext<{
  canGoBack: boolean;
  check: () => boolean;
}>({ canGoBack: false, check: () => false });

export function SiteHistory({ children }: { children: ReactNode }) {
  const location = useLocation();
  const action = useNavigationType();
  const previous = useRef<KnownEntry | null>(null);
  const observed = useRef(new Map<number, string>());
  const [status, setStatus] = useState<{
    key: string;
    allowed: boolean;
  } | null>(null);

  function fallbackCanGoBack() {
    const index = window.history.state?.idx;
    const key = window.history.state?.key ?? "default";
    return (
      Number.isInteger(index) &&
      observed.current.get(index) === key &&
      observed.current.has(index - 1)
    );
  }

  useEffect(() => {
    const nav = browserNavigation();
    const index = window.history.state?.idx;
    const key = window.history.state?.key ?? "default";
    if (Number.isInteger(index) && isSitePage(window.location.href)) {
      // Only trust entries actually observed in this document. A PUSH replaces
      // the forward branch; a previously unknown POP starts a new known segment.
      if (previous.current?.index === index && previous.current?.key === key) {
        // Repeated effect for the same entry (including StrictMode).
      } else if (action === "PUSH") {
        for (const i of observed.current.keys())
          if (i >= index) observed.current.delete(i);
        if (
          previous.current?.index !== index - 1 ||
          observed.current.get(index - 1) !== previous.current?.key
        )
          observed.current.clear();
      } else if (action === "POP" && observed.current.get(index) !== key) {
        observed.current.clear();
      } else if (action === "REPLACE" && previous.current?.index !== index) {
        observed.current.clear();
      }
      observed.current.set(index, key);
      previous.current = { index, key };
    } else {
      observed.current.clear();
      previous.current = null;
    }
    const update = () =>
      setStatus({
        key: location.key,
        allowed: nav ? nativeCanGoBack(nav) : fallbackCanGoBack(),
      });
    update();
    nav?.addEventListener("currententrychange", update);
    window.addEventListener("pageshow", update);
    return () => {
      nav?.removeEventListener("currententrychange", update);
      window.removeEventListener("pageshow", update);
    };
  }, [location.key, action]);

  const canGoBack = status?.key === location.key && status.allowed;
  return (
    <HistoryContext.Provider
      value={{
        canGoBack,
        check: () => {
          const nav = browserNavigation();
          return nav ? nativeCanGoBack(nav) : fallbackCanGoBack();
        },
      }}
    >
      {children}
    </HistoryContext.Provider>
  );
}

export function useSiteHistory() {
  return useContext(HistoryContext);
}
