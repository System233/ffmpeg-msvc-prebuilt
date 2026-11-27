import { useLoaderData, useParams, Link } from "react-router";
import { catalogSummary } from "../domain/catalog.server";
import { localized } from "../domain/catalog";
import { EntryLinks } from "../components/ReleaseDetail";
import { language, t } from "../lib/i18n";
export function loader() {
  return catalogSummary().master;
}
export const meta = () => [{ title: "Snapshots | FFmpeg MSVC Prebuilt" }];
export default function Master() {
  const data = useLoaderData<typeof loader>(),
    lang = language(useParams().lang);
  return (
    <>
      <div className="page-head">
        <h1>{t(lang, "Snapshots", "快照版本")}</h1>
        <p>
          {t(
            lang,
            "Upstream development snapshots. These are not stable releases.",
            "上游开发快照，不属于稳定发行版本。",
          )}
        </p>
      </div>
      {data.map((y, i) => (
        <section key={y.year} className="master-year">
          <div className="section-head">
            <h2>{y.year}</h2>
            <Link to={localized(lang, "/master/" + y.year + "/")}>
              {y.records.length} {t(lang, "builds", "批构建")} →
            </Link>
          </div>
          {i === 0 && (
            <EntryLinks entries={y.records.slice(0, 5)} lang={lang} />
          )}
        </section>
      ))}
    </>
  );
}
