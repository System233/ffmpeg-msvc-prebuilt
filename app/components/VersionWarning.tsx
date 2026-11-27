import { CircleAlert } from "lucide-react";
import { useEffect } from "react";
import { t, type Language } from "../i18n";
import { LicensingNoticeContent, licensingNoticeText } from "./VariantNotice";

type NoticeKind = "warning" | "lts";
const noticeIds = {
  warning: "build-warning-notice",
  lts: "lts-version-notice",
};
let activeKind: NoticeKind | null = null;
function activePopup() {
  return activeKind ? document.getElementById(noticeIds[activeKind]) : null;
}
function ltsText(lang: Language) {
  return t(lang, "warning.ltsDescription");
}
let activeAnchor: HTMLElement | null = null;
let leaveTimer: ReturnType<typeof setTimeout> | undefined;

function cancelDismiss() {
  clearTimeout(leaveTimer);
  leaveTimer = undefined;
}
function closeNotice() {
  cancelDismiss();
  const popup = activePopup();
  activeAnchor = null;
  activeKind = null;
  if (popup?.matches(":popover-open")) popup.hidePopover();
}
function scheduleDismiss(anchor?: HTMLElement) {
  if (anchor && anchor !== activeAnchor) return;
  cancelDismiss();
  leaveTimer = setTimeout(() => {
    const popup = activePopup();
    if (activeAnchor?.matches(":hover") || popup?.matches(":hover")) return;
    closeNotice();
  }, 180);
}

function positionNotice() {
  const anchor = activeAnchor;
  const popup = activePopup();
  if (!anchor || !popup?.matches(":popover-open")) return;
  const rect = anchor.getBoundingClientRect();
  const pad = 12,
    gap = 8;
  const viewport = window.visualViewport;
  const left = viewport?.offsetLeft ?? 0,
    top = viewport?.offsetTop ?? 0;
  const right = left + (viewport?.width ?? innerWidth);
  const bottom = top + (viewport?.height ?? innerHeight);
  const list = anchor.closest(".version-list")?.getBoundingClientRect();
  if (
    !anchor.isConnected ||
    rect.bottom <= Math.max(top, list?.top ?? top) ||
    rect.top >= Math.min(bottom, list?.bottom ?? bottom) ||
    rect.right <= left ||
    rect.left >= right
  ) {
    closeNotice();
    return;
  }
  popup.style.maxWidth = Math.max(1, right - left - pad * 2) + "px";
  popup.style.maxHeight = Math.max(1, bottom - top - pad * 2) + "px";
  const bounds = popup.getBoundingClientRect();
  const below = bottom - pad - rect.bottom - gap;
  const above = rect.top - top - pad - gap;
  const after = right - pad - rect.right - gap;
  const before = rect.left - left - pad - gap;
  let x = rect.left + (rect.width - bounds.width) / 2;
  let y = rect.bottom + gap;
  let side = "bottom";
  if (below < bounds.height) {
    if (above >= bounds.height) {
      y = rect.top - gap - bounds.height;
      side = "top";
    } else if (after >= bounds.width || before >= bounds.width) {
      const useAfter = after >= bounds.width;
      x = useAfter ? rect.right + gap : rect.left - gap - bounds.width;
      y = rect.top + (rect.height - bounds.height) / 2;
      side = useAfter ? "right" : "left";
    } else {
      const useBelow = below >= above;
      popup.style.maxHeight = Math.max(1, useBelow ? below : above) + "px";
      y = useBelow
        ? rect.bottom + gap
        : rect.top - gap - popup.getBoundingClientRect().height;
      side = useBelow ? "bottom" : "top";
    }
  }
  const measured = popup.getBoundingClientRect();
  popup.style.left =
    Math.max(left + pad, Math.min(x, right - pad - measured.width)) + "px";
  popup.style.top =
    Math.max(top + pad, Math.min(y, bottom - pad - measured.height)) + "px";
  popup.dataset.side = side;
}
function openNotice(anchor: HTMLElement, kind: NoticeKind) {
  const popup = document.getElementById(noticeIds[kind]);
  if (!popup) return;
  cancelDismiss();
  if (popup.matches(":popover-open") && activeAnchor === anchor) {
    positionNotice();
    return;
  }
  closeNotice();
  activeAnchor = anchor;
  activeKind = kind;
  if (!popup.matches(":popover-open")) popup.showPopover();
  positionNotice();
}

export function VersionWarningNotice({ lang }: { lang: Language }) {
  useEffect(() => {
    const dismiss = (e: PointerEvent) => {
      const popup = activePopup();
      if (
        popup?.matches(":popover-open") &&
        !popup.contains(e.target as Node) &&
        !(
          e.target instanceof Element &&
          e.target.closest("[data-version-notice]")
        )
      )
        closeNotice();
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && activePopup()?.matches(":popover-open")) {
        closeNotice();
        e.stopPropagation();
        e.preventDefault();
      }
    };
    const update = () => positionNotice();
    document.addEventListener("pointerdown", dismiss, true);
    document.addEventListener("keydown", escape, true);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
    return () => {
      document.removeEventListener("pointerdown", dismiss, true);
      document.removeEventListener("keydown", escape, true);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
      closeNotice();
    };
  }, []);
  return (
    <>
      {(["warning", "lts"] as const).map((kind) => (
        <div
          key={kind}
          id={noticeIds[kind]}
          popover="auto"
          className={
            kind === "warning"
              ? "version-warning-popover"
              : "version-lts-popover"
          }
          role="region"
          aria-label={
            kind === "warning"
              ? t(lang, "versionWarning.buildWarning")
              : t(lang, "versionWarning.longtermSupport")
          }
          onPointerEnter={(e) => {
            if (e.pointerType === "mouse") cancelDismiss();
          }}
          onPointerLeave={(e) => {
            if (e.pointerType === "mouse") scheduleDismiss();
          }}
          onToggle={(e) => {
            if (
              activeKind === kind &&
              !e.currentTarget.matches(":popover-open")
            ) {
              cancelDismiss();
              activeAnchor = null;
              activeKind = null;
            }
          }}
        >
          <p>
            {kind === "warning" ? (
              <LicensingNoticeContent lang={lang} onDetails={closeNotice} />
            ) : (
              ltsText(lang)
            )}
          </p>
        </div>
      ))}
    </>
  );
}

function NoticeTrigger({
  kind,
  lang,
  inOption = false,
}: {
  kind: NoticeKind;
  lang: Language;
  inOption?: boolean;
}) {
  const warning = kind === "warning";
  const label = warning
    ? t(lang, "versionWarning.viewWarning")
    : t(lang, "versionWarning.ltsLongtermSupport");
  const content = warning ? (
    <CircleAlert size={16} aria-hidden="true" />
  ) : (
    "LTS"
  );
  const className = warning ? "version-warning" : "version-badge";
  const hover = {
    onPointerEnter: (event: React.PointerEvent<HTMLElement>) => {
      if (event.pointerType === "mouse") openNotice(event.currentTarget, kind);
    },
    onPointerLeave: (event: React.PointerEvent<HTMLElement>) => {
      if (event.pointerType === "mouse") scheduleDismiss(event.currentTarget);
    },
  };
  if (inOption)
    return (
      <span
        className={className}
        data-version-notice={kind}
        {...hover}
        role="img"
        aria-label={warning ? licensingNoticeText(lang) : ltsText(lang)}
        onMouseUp={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          openNotice(e.currentTarget, kind);
        }}
      >
        {content}
      </span>
    );
  return (
    <button
      type="button"
      className={className}
      data-version-notice={kind}
      {...hover}
      aria-label={label}
      aria-controls={noticeIds[kind]}
      popoverTarget={noticeIds[kind]}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        openNotice(e.currentTarget, kind);
      }}
    >
      {content}
    </button>
  );
}

export function LtsBadge({
  lang,
  inOption = false,
}: {
  lang: Language;
  inOption?: boolean;
}) {
  return <NoticeTrigger kind="lts" lang={lang} inOption={inOption} />;
}

export function VersionWarning({
  warning,
  lang,
  inOption = false,
}: {
  warning: boolean;
  lang: Language;
  inOption?: boolean;
}) {
  return warning ? (
    <NoticeTrigger kind="warning" lang={lang} inOption={inOption} />
  ) : null;
}
