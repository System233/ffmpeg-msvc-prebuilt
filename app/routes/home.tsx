import { loadFAQ } from "../content/markdown.server";
import type { LoaderFunctionArgs } from "react-router";
import { VersionPicker } from "../components/VersionPicker";
import { HomeFAQ } from "../components/HomeFAQ";
import { useHydrated } from "../lib/hydration";
import { useEffect, useState } from "react";
import { Link, useLoaderData, useParams, useSearchParams } from "react-router";
import { ArrowDown, ArrowUpRight } from "lucide-react";
import { latest } from "../domain/catalog.server";
import {
  architectures,
  linkages,
  licenses,
  getVariant,
  parseVariant,
  toEntries,
  variantKey,
  type Entry,
  type Shard,
} from "../domain/catalog";
import { localized } from "../i18n/routing";
import { Segments } from "../components/ui";
import { PackageDownloads } from "../components/PackageDownloads";
import { language, linkageLabel, t } from "../i18n";
import { optionMeaning } from "../lib/option-copy";
export function loader({ params }: LoaderFunctionArgs) {
  return { ...latest(), faq: loadFAQ(language(params.lang)) };
}
export const meta = ({
  params,
}: {
  params: Record<string, string | undefined>;
}) => [
  { title: t(language(params.lang), "seo.homeTitle") },
  {
    name: "description",
    content: t(language(params.lang), "seo.homeDescription"),
  },
];
export default function Home() {
  const { options, search, initial, repo, faq } =
      useLoaderData<typeof loader>(),
    lang = language(useParams().lang);
  const [urlParams, setParams] = useSearchParams();
  const hydrated = useHydrated();
  const params = hydrated ? urlParams : new URLSearchParams();
  const requested = params.get("version");
  const option = requested
    ? search.find((o) => o.tag === requested)
    : options[0];
  const tag = option?.tag ?? "";
  const keys = option?.keys ?? [];
  const defaults = { arch: "x64", linkage: "shared", license: "lgpl" };
  const fields = ["arch", "linkage", "license"] as const;
  const selection = { ...defaults };
  for (const f of fields) {
    const value = params.get(f);
    if (
      value &&
      [...architectures, ...linkages, ...licenses].includes(value as never) &&
      (f === "arch"
        ? architectures
        : f === "linkage"
          ? linkages
          : licenses
      ).some((x) => x === value)
    )
      selection[f] = value;
  }
  const [cache, setCache] = useState<Record<string, Entry>>(() =>
    initial ? { [initial.tag]: initial } : {},
  );
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const entry = cache[tag];
  useEffect(() => {
    if (!option || entry) return;
    const controller = new AbortController();
    setError("");
    fetch(import.meta.env.BASE_URL + "data/" + option.shard + ".json", {
      signal: controller.signal,
    })
      .then((r) => {
        if (!r.ok) throw Error("HTTP " + r.status);
        return r.json() as Promise<Shard>;
      })
      .then((shard) => {
        const record = toEntries(shard, option.channel).find(
          (e) => e.tag === tag,
        );
        if (!record) throw Error("Catalog changed");
        if (!controller.signal.aborted)
          setCache((c) => ({ ...c, [tag]: record }));
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(String(e));
      });
    return () => controller.abort();
  }, [option, tag, entry, attempt]);
  function change(field: string, value: string) {
    setError("");
    const p = new URLSearchParams(params);
    p.set(field, value);
    setParams(p, { replace: true, preventScrollReset: true });
  }
  const available = keys.includes(
    variantKey(selection.arch, selection.linkage, selection.license),
  );
  const variant =
    entry &&
    getVariant(entry, selection.arch, selection.linkage, selection.license);
  const opts = (field: (typeof fields)[number], values: readonly string[]) =>
    values
      .map((value) => ({
        value,
        label:
          field === "linkage" ? linkageLabel(lang, value) : value.toUpperCase(),
        disabled: !keys.some((k) => parseVariant(k)[field] === value),
        tooltip: optionMeaning(lang, value),
      }))
      .filter(
        (o) =>
          !o.disabled || o.value === selection[field] || field !== "license",
      );
  const validChoices = keys.map(parseVariant);
  return (
    <div className="home-page">
      <section className="home-hero" aria-labelledby="hero-title">
        <h1 id="hero-title">
          FFmpeg <span>MSVC Prebuilt</span>
        </h1>
        <p>{t(lang, "home.intro")}</p>
        <div className="hero-actions">
          <a className="hero-primary" href="#download">
            {t(lang, "home.getFfmpeg")} <ArrowDown size={16} />
          </a>
          <Link className="hero-secondary" to={localized(lang, "/guide/")}>
            {t(lang, "nav.documentation")} <ArrowUpRight size={16} />
          </Link>
        </div>
        {initial?.channel === "release" && (
          <p className="hero-release">
            <span>{t(lang, "home.latestStable")}</span>{" "}
            <Link to={localized(lang, "/releases/" + initial.upstream + "/")}>
              FFmpeg {initial.upstream}
            </Link>
            <time>{initial.date}</time>
          </p>
        )}
      </section>
      <section className="quick" id="download" aria-labelledby="download-title">
        <div className="section-head">
          <h2 id="download-title">{t(lang, "home.downloadFfmpeg")}</h2>
          <Link to={localized(lang, "/releases/")}>
            {t(lang, "home.allReleases")} <ArrowUpRight size={14} />
          </Link>
        </div>
        {option ? (
          <>
            <div className="quick-filters">
              <VersionPicker
                lang={lang}
                options={search}
                value={tag}
                onChange={(v) => change("version", v)}
              />
              <Segments
                label={t(lang, "common.architecture")}
                value={selection.arch}
                options={opts("arch", architectures)}
                onChange={(v) => change("arch", v)}
              />
              <Segments
                label={t(lang, "home.linkage")}
                value={selection.linkage}
                options={opts("linkage", linkages)}
                onChange={(v) => change("linkage", v)}
              />
              <Segments
                label={t(lang, "home.license")}
                value={selection.license}
                options={opts("license", licenses)}
                onChange={(v) => change("license", v)}
              />
            </div>
            <div className="quick-result" aria-live="polite">
              {!available ? (
                <div className="unavailable-box">
                  <strong>
                    {t(lang, "home.thisConfigurationIsUnavailable")}
                  </strong>
                  <p className="muted">
                    {t(lang, "home.selectAvailableConfiguration")}
                  </p>
                  <div className="available-options">
                    {validChoices.map((v) => (
                      <button
                        key={variantKey(v.arch, v.linkage, v.license)}
                        className="text-button"
                        onClick={() => {
                          const p = new URLSearchParams(params);
                          for (const f of fields) p.set(f, v[f]);
                          setParams(p, {
                            replace: true,
                            preventScrollReset: true,
                          });
                        }}
                      >
                        {v.arch.toUpperCase()} ·{" "}
                        {linkageLabel(lang, v.linkage, true)} ·{" "}
                        {v.license.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>
              ) : variant && entry ? (
                <>
                  <PackageDownloads
                    variant={variant}
                    linkage={selection.linkage}
                    tag={tag}
                    repo={repo}
                    lang={lang}
                    label={
                      selection.arch.toUpperCase() +
                      " · " +
                      linkageLabel(lang, selection.linkage, true) +
                      " · " +
                      selection.license.toUpperCase()
                    }
                    date={entry.date}
                  />
                  <div className="quick-info">
                    <span className="muted">
                      {entry.date} · {selection.arch.toUpperCase()} ·{" "}
                      {linkageLabel(lang, selection.linkage, true)} ·{" "}
                      {selection.license.toUpperCase()}
                    </span>
                  </div>
                </>
              ) : error ? (
                <div role="alert">
                  {t(lang, "home.unableToLoadThisBuild")}{" "}
                  <button
                    className="text-button"
                    onClick={() => setAttempt((n) => n + 1)}
                  >
                    {t(lang, "home.retry")}
                  </button>
                </div>
              ) : (
                <p className="muted">{t(lang, "home.loadingBuildDetails")}</p>
              )}
            </div>
            <div className="quick-bottom">
              <Link to={localized(lang, "/build/" + tag + "/")}>
                {t(lang, "home.viewAllVariants")} →
              </Link>
              <Link to={localized(lang, "/guide/")}>
                {t(lang, "home.whichPackageShouldIChoose")}
              </Link>
            </div>
          </>
        ) : (
          <p>
            {requested
              ? t(lang, "home.thisBuildIsUnavailable")
              : t(lang, "home.noVersionsAvailable")}{" "}
            {requested && (
              <button
                className="text-button"
                onClick={() => {
                  const p = new URLSearchParams(params);
                  p.delete("version");
                  setParams(p, { replace: true });
                }}
              >
                {t(lang, "home.selectLatest")}
              </button>
            )}
          </p>
        )}
      </section>
      <div className="home-links">
        <Link to={localized(lang, "/releases/")}>
          <strong>{t(lang, "nav.releases")}</strong>
          <span className="muted">{t(lang, "home.browseStableReleases")}</span>
          <ArrowUpRight size={18} />
        </Link>
        <Link to={localized(lang, "/master/")}>
          <strong>{t(lang, "nav.snapshots")}</strong>
          <span className="muted">
            {t(lang, "home.upstreamDevelopmentSnapshots")}
          </span>
          <ArrowUpRight size={18} />
        </Link>
      </div>
      <HomeFAQ lang={lang} questions={faq} />
    </div>
  );
}
