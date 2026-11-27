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
  localized,
  parseVariant,
  toEntries,
  variantKey,
  type Entry,
  type Shard,
} from "../domain/catalog";
import { Segments } from "../components/ui";
import { PackageDownloads } from "../components/PackageDownloads";
import { language, linkageLabel, t } from "../lib/i18n";
import { optionMeaning } from "../lib/option-copy";
export function loader() {
  return latest();
}
export const meta = () => [
  { title: "FFmpeg MSVC Prebuilt – Windows downloads" },
  {
    name: "description",
    content: "Native Windows FFmpeg builds compiled with MSVC.",
  },
];
export default function Home() {
  const { options, search, initial, repo } = useLoaderData<typeof loader>(),
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
        <p>
          {t(
            lang,
            "Native FFmpeg builds for Windows, compiled with Microsoft Visual C++. Ready-to-use binaries and native SDKs.",
            "使用 Microsoft Visual C++ 编译的 Windows 原生 FFmpeg 构建，提供可直接使用的二进制包与原生 SDK。",
          )}
        </p>
        <div className="hero-actions">
          <a className="hero-primary" href="#download">
            {t(lang, "Get FFmpeg", "获取 FFmpeg")} <ArrowDown size={16} />
          </a>
          <Link className="hero-secondary" to={localized(lang, "/guide/")}>
            {t(lang, "Documentation", "使用文档")} <ArrowUpRight size={16} />
          </Link>
        </div>
        {initial?.channel === "release" && (
          <p className="hero-release">
            <span>{t(lang, "Latest stable", "最新发行版")}</span>{" "}
            <Link to={localized(lang, "/releases/" + initial.upstream + "/")}>
              FFmpeg {initial.upstream}
            </Link>
            <time>{initial.date}</time>
          </p>
        )}
      </section>
      <section className="quick" id="download" aria-labelledby="download-title">
        <div className="section-head">
          <h2 id="download-title">
            {t(lang, "Download FFmpeg", "下载 FFmpeg")}
          </h2>
          <Link to={localized(lang, "/releases/")}>
            {t(lang, "All releases", "全部版本")} <ArrowUpRight size={14} />
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
                label={t(lang, "Architecture", "架构")}
                value={selection.arch}
                options={opts("arch", architectures)}
                onChange={(v) => change("arch", v)}
              />
              <Segments
                label={t(lang, "Linkage", "链接方式")}
                value={selection.linkage}
                options={opts("linkage", linkages)}
                onChange={(v) => change("linkage", v)}
              />
              <Segments
                label={t(lang, "License", "许可证")}
                value={selection.license}
                options={opts("license", licenses)}
                onChange={(v) => change("license", v)}
              />
            </div>
            <div className="quick-result" aria-live="polite">
              {!available ? (
                <div className="unavailable-box">
                  <strong>
                    {t(
                      lang,
                      "This configuration is unavailable",
                      "当前构建组合不可用",
                    )}
                  </strong>
                  <p className="muted">
                    {t(
                      lang,
                      "Select an available combination explicitly. Your license selection will not change automatically.",
                      "请明确选择可用组合，许可证不会自动切换。",
                    )}
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
                  {t(lang, "Unable to load this build.", "无法加载构建详情。")}{" "}
                  <button
                    className="text-button"
                    onClick={() => setAttempt((n) => n + 1)}
                  >
                    {t(lang, "Retry", "重试")}
                  </button>
                </div>
              ) : (
                <p className="muted">
                  {t(lang, "Loading build details…", "正在加载构建详情…")}
                </p>
              )}
            </div>
            <div className="quick-bottom">
              <Link to={localized(lang, "/build/" + tag + "/")}>
                {t(lang, "View all variants", "查看全部变体")} →
              </Link>
              <Link to={localized(lang, "/guide/")}>
                {t(lang, "Which package should I choose?", "如何选择构建包？")}
              </Link>
            </div>
          </>
        ) : (
          <p>
            {requested
              ? t(lang, "This build is unavailable.", "指定的构建不可用。")
              : t(lang, "No versions available.", "暂无可用版本。")}{" "}
            {requested && (
              <button
                className="text-button"
                onClick={() => {
                  const p = new URLSearchParams(params);
                  p.delete("version");
                  setParams(p, { replace: true });
                }}
              >
                {t(lang, "Select latest", "选择最新版本")}
              </button>
            )}
          </p>
        )}
      </section>
      <div className="home-links">
        <Link to={localized(lang, "/releases/")}>
          <strong>{t(lang, "All versions", "全部版本")}</strong>
          <span className="muted">
            {t(lang, "Browse stable releases", "浏览稳定版本")}
          </span>
          <ArrowUpRight size={18} />
        </Link>
        <Link to={localized(lang, "/master/")}>
          <strong>{t(lang, "Snapshots", "快照版本")}</strong>
          <span className="muted">
            {t(lang, "Upstream development snapshots", "上游最新构建快照")}
          </span>
          <ArrowUpRight size={18} />
        </Link>
      </div>
      <HomeFAQ lang={lang} />
    </div>
  );
}
