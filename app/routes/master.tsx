import { useLoaderData, useParams, Link } from "react-router";
import { catalogSummary } from "../domain/catalog.server";
import { localized } from "../i18n/routing";
import { EntryLinks } from "../components/ReleaseDetail";
import { language, t, countLabel } from "../i18n";
export function loader() {
  return catalogSummary().master;
}
export const meta = ({
  params,
}: {
  params: Record<string, string | undefined>;
}) => [
  {
    title:
      t(language(params.lang), "seo.masterTitle") + " | FFmpeg MSVC Prebuilt",
  },
];
export default function Master() {
  const data = useLoaderData<typeof loader>(),
    lang = language(useParams().lang);
  return (
    <>
      <div className="page-head">
        <h1>{t(lang, "nav.snapshots")}</h1>
        <p>{t(lang, "master.description")}</p>
      </div>
      {data.map((y, i) => (
        <section key={y.year} className="master-year">
          <div className="section-head">
            <h2>{y.year}</h2>
            <Link to={localized(lang, "/master/" + y.year + "/")}>
              {countLabel(lang, "common.buildCount", y.records.length)} →
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
