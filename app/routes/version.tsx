import { LtsBadge } from "../components/VersionWarning";
import { HistoryBack } from "../components/HistoryBack";
import { useLoaderData, useParams } from "react-router";
import type { LoaderFunctionArgs } from "react-router";
import {
  entries,
  findBuild,
  repo,
  majorEntries,
} from "../domain/catalog.server";
import { ReleaseDetail, EntryLinks } from "../components/ReleaseDetail";
import { majorVersion, hasWarning } from "../domain/catalog";
import { language, t } from "../i18n";

export function loader({ params }: LoaderFunctionArgs) {
  const version = params.version ?? "";
  const records = entries("releases/" + version);
  const entry = records[0] ?? findBuild(version);
  if (!entry) throw new Response("Not found", { status: 404 });
  const related =
    entry.channel === "release"
      ? majorEntries(majorVersion(entry.upstream))
      : [];
  const versions = related
    .filter((v) => v.version !== entry.upstream)
    .map((v) => v.records[0]);
  const builds = entries("releases/" + entry.upstream)
    .filter((e) => e.tag !== entry.tag)
    .map((e) => ({
      tag: e.tag,
      date: e.date,
      upstream: e.upstream,
      lts: e.lts,
      warning: hasWarning(e),
    }));
  return { entry, versions, builds, repo };
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
      "FFmpeg " +
      (data?.entry.upstream ??
        t(language(params.lang), "seo.releaseFallback")) +
      " | MSVC Prebuilt",
  },
];

function SectionJump({
  id,
  children,
}: {
  id: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={"#" + id}
      onClick={(e) => {
        if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey)
          return;
        const section = document.getElementById(id);
        if (!section) return;
        e.preventDefault();
        section.scrollIntoView({ block: "start" });
      }}
    >
      {children} ↓
    </a>
  );
}
export default function Version() {
  const { entry, versions, builds, repo } = useLoaderData<typeof loader>(),
    lang = language(useParams().lang);
  return (
    <>
      <div className="page-head">
        <HistoryBack
          lang={lang}
          parent="/releases/"
          parentLabel={t(lang, "version.backToAllVersions")}
        />
        <h1>FFmpeg {entry.upstream}</h1>
        <div className="meta-line">
          {entry.lts && <LtsBadge lang={lang} />}
          <time>{entry.date}</time>
          <span className="mono">{entry.tag}</span>
          {versions.length > 0 && (
            <SectionJump id="history">
              {t(lang, "version.otherVersions")}
            </SectionJump>
          )}
          {builds.length > 0 && (
            <SectionJump id="builds">
              {t(lang, "version.otherBuilds")}
            </SectionJump>
          )}
        </div>
      </div>
      <ReleaseDetail key={entry.tag} entry={entry} repo={repo} lang={lang} />
      {versions.length > 0 && (
        <section className="history" id="history">
          <h2>{t(lang, "version.otherVersions")}</h2>
          <EntryLinks entries={versions} lang={lang} kind="version" />
        </section>
      )}
      {builds.length > 0 && (
        <section className="history" id="builds">
          <h2>{t(lang, "version.otherBuilds")}</h2>
          <EntryLinks entries={builds} lang={lang} />
        </section>
      )}
    </>
  );
}
