import { VersionWarning, LtsBadge } from "./VersionWarning";
import { VariantNotice } from "./VariantNotice";
import { PackageNoteText } from "./PackageNoteText";
import { describeAssets } from "../domain/assets";
import { assetLabel, packageNote } from "../lib/asset-copy";
import { useHydrated } from "../lib/hydration";
import { Link, useSearchParams } from "react-router";
import { AssetLink, AssetInspector, Segments } from "./ui";
import {
  architectures,
  linkages,
  licenses,
  parseVariant,
  localized,
  variantKey,
  type Entry,
  type Variant,
} from "../domain/catalog";
import { linkageLabel, t, type Language } from "../lib/i18n";
import { optionMeaning } from "../lib/option-copy";
export function ReleaseDetail({
  entry,
  repo,
  lang,
}: {
  entry: Entry;
  repo: string;
  lang: Language;
}) {
  const keys = Object.keys(entry.variants);
  const note = packageNote(
    Object.entries(entry.variants).flatMap(([k, v]) =>
      describeAssets(v, parseVariant(k).linkage),
    ),
    lang,
  );
  const rows = architectures.filter((a) =>
    keys.some((k) => parseVariant(k).arch === a),
  );
  const groups = linkages
    .map((linkage) => ({
      linkage,
      licenses: licenses.filter((license) =>
        keys.some((k) => {
          const v = parseVariant(k);
          return v.linkage === linkage && v.license === license;
        }),
      ),
    }))
    .filter((g) => g.licenses.length);
  const [params, setParams] = useSearchParams();
  const hydrated = useHydrated();
  const requested = hydrated ? params.get("arch") : null;
  const arch = rows.find((a) => a === requested) ?? rows[0];
  const mobileNote = packageNote(
    Object.entries(entry.variants)
      .filter(([k]) => parseVariant(k).arch === arch)
      .flatMap(([k, v]) => describeAssets(v, parseVariant(k).linkage)),
    lang,
  );
  function chooseArch(next: string) {
    const p = new URLSearchParams(params);
    p.set("arch", next);
    setParams(p, { replace: true, preventScrollReset: true });
  }
  const renderCell = (
    v: Variant | undefined,
    label: string,
    linkage: string,
  ) =>
    v ? (
      <div className="matrix-cell">
        <div className="matrix-actions">
          {describeAssets(v, linkage).map((d) => (
            <AssetLink
              key={d.kind}
              tooltip={optionMeaning(lang, d.kind)}
              asset={d.asset}
              tag={entry.tag}
              repo={repo}
              lang={lang}
            >
              {assetLabel(d.kind, lang, true)}
            </AssetLink>
          ))}
        </div>
        <AssetInspector
          linkage={linkage}
          variant={v}
          tag={entry.tag}
          repo={repo}
          lang={lang}
          label={label}
          date={entry.date}
        />
      </div>
    ) : (
      <span
        className="unavailable"
        aria-label={t(lang, "Not available", "不可用")}
      >
        —
      </span>
    );
  return (
    <section className="build-section">
      <div className="section-head">
        <div>
          <h2>{t(lang, "Build variants", "构建变体")}</h2>
          <p className="muted">
            {keys.length} {t(lang, "variants", "种变体")}
          </p>
        </div>
        <a
          className="subtle-link"
          href={repo + "/releases/tag/" + encodeURIComponent(entry.tag)}
        >
          GitHub Release ↗
        </a>
      </div>
      <VariantNotice
        note={Object.values(entry.variants).find((v) => v.note)?.note}
        lang={lang}
      />
      <div className="mobile-architecture">
        <Segments
          label={t(lang, "Architecture", "架构")}
          value={arch}
          options={rows.map((a) => ({
            value: a,
            label: a.toUpperCase(),
            tooltip: optionMeaning(lang, a),
          }))}
          onChange={chooseArch}
        />
      </div>
      <div
        className="build-matrix"
        style={
          {
            "--matrix-columns": groups.reduce(
              (n, g) => n + g.licenses.length,
              0,
            ),
          } as React.CSSProperties
        }
      >
        {rows.map((a, i) => (
          <section
            className={"matrix-row" + (a === arch ? " is-selected" : "")}
            key={a}
            aria-label={a.toUpperCase()}
          >
            <h3 className="matrix-arch">{a.toUpperCase()}</h3>
            {groups.map((g) => (
              <div
                key={g.linkage}
                className="matrix-group"
                style={
                  {
                    "--group-columns": g.licenses.length,
                  } as React.CSSProperties
                }
              >
                <h4
                  className={"matrix-group-title" + (i === 0 ? " first" : "")}
                >
                  {linkageLabel(lang, g.linkage)}
                </h4>
                <div className="matrix-group-grid">
                  {g.licenses.map((l) => (
                    <div key={l} className="matrix-slot">
                      <h5
                        className={"matrix-license" + (i === 0 ? " first" : "")}
                      >
                        {l.toUpperCase()}
                      </h5>
                      {renderCell(
                        entry.variants[variantKey(a, g.linkage, l)],
                        a.toUpperCase() +
                          " · " +
                          linkageLabel(lang, g.linkage, true) +
                          " · " +
                          l.toUpperCase(),
                        g.linkage,
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </section>
        ))}
      </div>
      <noscript>
        <style>
          {
            ".matrix-row{display:grid!important}.mobile-architecture{display:none!important}.matrix-note-all{display:inline!important}.matrix-note-current{display:none!important}"
          }
        </style>
      </noscript>
      {note && (
        <p className="matrix-note muted">
          <span className="matrix-note-all">
            <PackageNoteText note={note} lang={lang} />
          </span>
          <span className="matrix-note-current">
            <PackageNoteText note={mobileNote} lang={lang} />
          </span>
        </p>
      )}
    </section>
  );
}
export function EntryLinks({
  entries,
  lang,
  kind = "build",
}: {
  entries: {
    tag: string;
    date: string;
    upstream: string;
    warning?: boolean;
    lts?: boolean;
  }[];
  lang: Language;
  kind?: "version" | "build";
}) {
  return (
    <div className="release-list">
      {entries.map((e) => (
        <div className="release-row" key={e.tag}>
          <div className="release-name">
            <Link
              className="release-row-target"
              to={localized(
                lang,
                kind === "version"
                  ? "/releases/" + e.upstream + "/"
                  : "/build/" + e.tag + "/",
              )}
            >
              <strong>{e.upstream}</strong>
            </Link>
            {e.lts && <LtsBadge lang={lang} />}
            <VersionWarning warning={!!e.warning} lang={lang} />
            <span className="muted mono">{e.tag}</span>
          </div>
          <time>{e.date}</time>
          <span aria-hidden>{kind === "version" ? "→" : "↗"}</span>
        </div>
      ))}
    </div>
  );
}
