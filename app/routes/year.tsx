import { HistoryBack } from "../components/HistoryBack";
import { useLoaderData, useParams } from "react-router";
import type { LoaderFunctionArgs } from "react-router";
import { hasWarning } from "../domain/catalog";
import { entries } from "../domain/catalog.server";
import { EntryLinks } from "../components/ReleaseDetail";
import { language, t, countLabel } from "../i18n";
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
export const meta = ({
  data,
  params,
}: {
  data?: ReturnType<typeof loader>;
  params: Record<string, string | undefined>;
}) => [
  {
    title:
      t(language(params.lang), "seo.yearTitle", { year: data?.year ?? "" }) +
      " | FFmpeg MSVC Prebuilt",
  },
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
          parentLabel={t(lang, "year.backToSnapshots")}
        />
        <h1>{t(lang, "seo.yearTitle", { year: year ?? "" })}</h1>
        <p>{countLabel(lang, "common.snapshotCount", records.length)}</p>
      </div>
      <EntryLinks entries={records} lang={lang} />
    </>
  );
}
