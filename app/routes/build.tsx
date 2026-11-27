import { LtsBadge } from "../components/VersionWarning";
import { HistoryBack } from "../components/HistoryBack";
import { useLoaderData, useParams } from "react-router";
import type { LoaderFunctionArgs } from "react-router";
import { findBuild, repo } from "../domain/catalog.server";
import { ReleaseDetail } from "../components/ReleaseDetail";
import { language, t } from "../i18n";
export function loader({ params }: LoaderFunctionArgs) {
  const entry = findBuild(params.tag ?? "");
  if (!entry) throw new Response("Not found", { status: 404 });
  return { entry, repo };
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
      (data?.entry.tag ?? t(language(params.lang), "seo.buildFallback")) +
      " | FFmpeg MSVC Prebuilt",
  },
];
export default function Build() {
  const { entry, repo } = useLoaderData<typeof loader>(),
    lang = language(useParams().lang);
  return (
    <>
      <div className="page-head">
        <HistoryBack
          lang={lang}
          parent={
            entry.channel === "master"
              ? "/master/" + entry.date.slice(0, 4) + "/"
              : "/releases/" + entry.upstream + "/"
          }
          parentLabel={
            entry.channel === "master"
              ? t(lang, "build.backToYear", { year: entry.date.slice(0, 4) })
              : t(lang, "build.backToVersion", { version: entry.upstream })
          }
        />
        <h1>FFmpeg {entry.upstream}</h1>
        <div className="meta-line">
          {entry.lts && <LtsBadge lang={lang} />}
          <time>{entry.date}</time>
          <span className="mono">{entry.tag}</span>
          {entry.commit && (
            <a
              href={"https://github.com/FFmpeg/FFmpeg/commit/" + entry.commit}
              title={entry.commit}
            >
              {entry.commit.slice(0, 12)} ↗
            </a>
          )}
        </div>
      </div>
      <ReleaseDetail key={entry.tag} entry={entry} repo={repo} lang={lang} />
    </>
  );
}
