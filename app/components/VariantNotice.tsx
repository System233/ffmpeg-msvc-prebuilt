import { CircleAlert } from "lucide-react";
import { Link } from "react-router";
import { localized, type Variant } from "../domain/catalog";
import { t, type Language } from "../lib/i18n";

export function licensingNoticePath(lang: Language) {
  return (
    localized(lang, "/history/") +
    t(lang, "#legacy-lgpl-builds", "#历史-lgpl-构建")
  );
}
export function licensingNoticeText(lang: Language) {
  return t(
    lang,
    "The LGPL variant of this build contains GPL-licensed components and should not be treated as a verified LGPL build.",
    "此构建的 LGPL 版本包含 GPL 许可组件，不能视为已确认合规的 LGPL 构建。",
  );
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
          {t(lang, "View details", "查看详情")} ↗
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
