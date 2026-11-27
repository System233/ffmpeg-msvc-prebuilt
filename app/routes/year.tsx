import { HistoryBack } from "../components/HistoryBack";
import { useLoaderData, useParams } from "react-router";
import type { LoaderFunctionArgs } from "react-router";
import { hasWarning } from "../domain/catalog";
import { entries } from "../domain/catalog.server";
import { EntryLinks } from "../components/ReleaseDetail";
import { language, t } from "../lib/i18n";
export function loader({ params }: LoaderFunctionArgs) {
  const data = entries("master/" + params.year);
  if (!data.length) throw new Response("Not found", { status: 404 });
  return {
    year: params.year,
    records: data.map((e) => ({
      tag: e.tag,
      date: e.date,
      upstream: e.upstream,
      warning: hasWarning(e),
    })),
  };
}
export const meta = ({ data }: any) => [
  { title: "Snapshots " + (data?.year ?? "") + " | FFmpeg MSVC Prebuilt" },
];
export default function Year() {
  const { year, records } = useLoaderData<typeof loader>(),
    lang = language(useParams().lang);
  return (
    <>
      <div className="page-head">
        <HistoryBack
          lang={lang}
          parent="/master/"
          parentLabel={t(lang, "Back to snapshots", "返回快照版本")}
        />
        <h1>
          {t(lang, "Snapshots", "快照版本")} {year}
        </h1>
        <p>
          {records.length} {t(lang, "snapshots", "个快照版本")}
        </p>
      </div>
      <EntryLinks entries={records} lang={lang} />
    </>
  );
}
