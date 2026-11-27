import { VersionSearch } from "../components/VersionSearch";
import { useHydrated } from "../lib/hydration";
import { useLoaderData, useParams, Link, useSearchParams } from "react-router";
import { ChevronRight } from "lucide-react";
import { VersionWarning, LtsBadge } from "../components/VersionWarning";
import { searchOptions } from "../domain/catalog.server";
import {
  localized,
  filterVersionOptions,
  majorVersion,
  versionHeads,
} from "../domain/catalog";
import { language, t, countLabel } from "../i18n";
export function loader() {
  return searchOptions().filter((o) => o.channel === "release");
}
export const meta = ({
  params,
}: {
  params: Record<string, string | undefined>;
}) => [
  {
    title:
      t(language(params.lang), "seo.releasesTitle") + " | FFmpeg MSVC Prebuilt",
  },
];
export default function Releases() {
  const data = useLoaderData<typeof loader>(),
    lang = language(useParams().lang);
  const [params, setParams] = useSearchParams();
  const hydrated = useHydrated();
  const query = hydrated ? (params.get("q") ?? "") : "";
  const onlyLts = hydrated && params.get("lts") === "1";
  const filtered = filterVersionOptions(
    data,
    onlyLts ? "lts" : "all",
    query,
    "catalog",
  );
  const normalized = query
    .trim()
    .toLowerCase()
    .replace(/^ffmpeg\s+/, "");
  const grouped = !query.trim();
  const heads = versionHeads(data);
  const latestTag = heads[0]?.tag;
  const headTags = new Set(heads.map((v) => v.tag));
  const families = [...new Set(filtered.map((v) => majorVersion(v.upstream)))];
  return (
    <>
      <div className="page-head">
        <h1>{t(lang, "nav.releases")}</h1>
        <p>
          {grouped
            ? countLabel(lang, "releases.majorCount", families.length)
            : countLabel(lang, "releases.resultCount", filtered.length)}
        </p>
      </div>
      <div className="release-search">
        <span className="field-label">
          {t(lang, "versionPicker.searchVersions")}
        </span>
        <VersionSearch
          lang={lang}
          filter={onlyLts ? "lts" : "all"}
          onFilterChange={(filter) => {
            const p = new URLSearchParams(params);
            if (filter === "lts") p.set("lts", "1");
            else p.delete("lts");
            setParams(p, { replace: true, preventScrollReset: true });
          }}
        >
          <input
            type="search"
            aria-label={t(lang, "versionPicker.searchVersions")}
            placeholder={t(lang, "releases.searchPlaceholder")}
            value={query}
            onChange={(e) => {
              const p = new URLSearchParams(params);
              if (e.target.value) p.set("q", e.target.value);
              else p.delete("q");
              setParams(p, { replace: true, preventScrollReset: true });
            }}
          />
        </VersionSearch>
      </div>
      {families.map((f) => {
        const rows = filtered.filter((v) => majorVersion(v.upstream) === f);
        return (
          <section className="release-family" key={f}>
            {grouped ? (
              <div className="release-row">
                <div className="release-name">
                  <Link
                    className="release-row-target"
                    to={localized(lang, "/releases/" + rows[0].upstream + "/")}
                  >
                    <strong>FFmpeg {f}</strong>
                  </Link>
                  <span className="release-series-summary">
                    {rows.map((v) => (
                      <span key={v.tag} className="release-series-item">
                        {v.upstream}
                        {v.tag === latestTag && (
                          <span className="latest-label">
                            {t(lang, "versionPicker.latest")}
                          </span>
                        )}
                        {v.lts && <LtsBadge lang={lang} />}
                      </span>
                    ))}
                  </span>
                </div>
                <span className="release-count">
                  {countLabel(lang, "common.variantCount", rows[0].keys.length)}
                  {data.filter((v) => majorVersion(v.upstream) === f).length > 1
                    ? " · " +
                      countLabel(
                        lang,
                        "common.buildCount",
                        data.filter((v) => majorVersion(v.upstream) === f)
                          .length,
                      )
                    : ""}
                </span>
                <time>{rows[0].date}</time>
                <ChevronRight size={16} />
              </div>
            ) : (
              <>
                <h2>FFmpeg {f}</h2>
                {rows.map((v) => (
                  <div className="release-row" key={v.tag}>
                    <div className="release-name">
                      <Link
                        className="release-row-target"
                        to={localized(
                          lang,
                          !headTags.has(v.tag) ||
                            normalized === v.tag.toLowerCase()
                            ? "/build/" + v.tag + "/"
                            : "/releases/" + v.upstream + "/",
                        )}
                      >
                        <strong>FFmpeg {v.upstream}</strong>
                      </Link>
                      {v.tag === latestTag && (
                        <span className="latest-label">
                          {t(lang, "versionPicker.latest")}
                        </span>
                      )}
                      {!headTags.has(v.tag) && (
                        <span className="muted mono">{v.tag}</span>
                      )}
                      {v.lts && <LtsBadge lang={lang} />}
                      <VersionWarning warning={v.warning} lang={lang} />
                    </div>
                    <span className="release-count">
                      {countLabel(lang, "common.variantCount", v.keys.length)}
                      {data.filter((o) => o.upstream === v.upstream).length > 1
                        ? " · " +
                          countLabel(
                            lang,
                            "common.buildCount",
                            data.filter((o) => o.upstream === v.upstream)
                              .length,
                          )
                        : ""}
                    </span>
                    <time>{v.date}</time>
                    <ChevronRight size={16} />
                  </div>
                ))}
              </>
            )}
          </section>
        );
      })}
      {!filtered.length && (
        <p className="empty">{t(lang, "versionPicker.noMatchingVersions")}</p>
      )}
    </>
  );
}
