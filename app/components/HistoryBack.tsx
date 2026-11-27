import { ArrowLeft } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { t, type Language } from "../lib/i18n";
import { localized } from "../domain/catalog";
import { useSiteHistory } from "../lib/site-history";

export function HistoryBack({
  lang,
  parent,
  parentLabel,
}: {
  lang: Language;
  parent: string;
  parentLabel: string;
}) {
  const navigate = useNavigate();
  const { canGoBack, check } = useSiteHistory();
  const target = localized(lang, parent);
  if (!canGoBack)
    return (
      <Link className="history-back" to={target} replace>
        <ArrowLeft size={14} aria-hidden="true" />
        {parentLabel}
      </Link>
    );
  return (
    <button
      type="button"
      className="history-back"
      onClick={() => {
        if (check()) navigate(-1);
        else navigate(target, { replace: true });
      }}
    >
      <ArrowLeft size={14} aria-hidden="true" />
      {t(lang, "Back", "返回")}
    </button>
  );
}
