import { CircleAlert } from "lucide-react";
import { Link } from "react-router";
import type { Variant } from "../domain/catalog";
import { localized } from "../i18n/routing";
import { t, type Language } from "../i18n";

export function licensingNoticePath(lang: Language) {
  return localized(lang, "/history/") + t(lang, "warning.legacyLgplAnchor");
}
export function licensingNoticeText(lang: Language) {
  return t(lang, "warning.legacyLgplDescription");
}

export function LicensingNoticeContent({
  lang,
  onDetails,
}: {
  lang: Language;
  onDetails?: () => void;
}) {
  return (
    <>
      <CircleAlert className="notice-icon" size={16} aria-hidden="true" />
      <span>
        {licensingNoticeText(lang)}{" "}
        <Link to={licensingNoticePath(lang)} onClick={onDetails}>
          {t(lang, "variantNotice.viewDetails")} ↗
        </Link>
      </span>
    </>
  );
}

export function VariantNotice({
  note,
  lang,
}: {
  note: Variant["note"];
  lang: Language;
}) {
  if (note !== "legacy-lgpl-licensing") return null;
  return (
    <p className="variant-notice">
      <LicensingNoticeContent lang={lang} />
    </p>
  );
}
