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
import { language, t } from "../lib/i18n";
export function loader() {
  return searchOptions().filter((o) => o.channel === "release");
}
export const meta = () => [{ title: "All versions | FFmpeg MSVC Prebuilt" }];
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
        <h1>{t(lang, "All versions", "全部版本")}</h1>
        <p>
          {grouped ? families.length : filtered.length}{" "}
          {grouped
            ? t(
                lang,
                families.length === 1 ? "major version" : "major versions",
                "个主版本",
              )
            : t(lang, filtered.length === 1 ? "result" : "results", "条结果")}
        </p>
      </div>
      <div className="release-search">
        <span className="field-label">
          {t(lang, "Search versions", "搜索版本")}
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
            aria-label={t(lang, "Search versions", "搜索版本")}
            placeholder="9.1, 8.1, tag…"
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
                            {t(lang, "Latest", "最新")}
                          </span>
                        )}
                        {v.lts && <LtsBadge lang={lang} />}
                      </span>
                    ))}
                  </span>
                </div>
                <span className="release-count">
                  {rows[0].keys.length} {t(lang, "variants", "种变体")}
                  {data.filter((v) => majorVersion(v.upstream) === f).length > 1
                    ? " · " +
                      data.filter((v) => majorVersion(v.upstream) === f)
                        .length +
                      " " +
                      t(lang, "builds", "批构建")
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
                          {t(lang, "Latest", "最新")}
                        </span>
                      )}
                      {!headTags.has(v.tag) && (
                        <span className="muted mono">{v.tag}</span>
                      )}
                      {v.lts && <LtsBadge lang={lang} />}
                      <VersionWarning warning={v.warning} lang={lang} />
                    </div>
                    <span className="release-count">
                      {v.keys.length} {t(lang, "variants", "种变体")}
                      {data.filter((o) => o.upstream === v.upstream).length > 1
                        ? " · " +
                          data.filter((o) => o.upstream === v.upstream).length +
                          " " +
                          t(lang, "builds", "批构建")
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
        <p className="empty">
          {t(lang, "No matching versions.", "没有匹配的版本。")}
        </p>
      )}
    </>
  );
}
