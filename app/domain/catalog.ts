import type { CatalogIndex } from "../../.generated/index-types";
import type { CatalogShard } from "../../.generated/shard-types";
export type Index = CatalogIndex;
export type Shard = CatalogShard;
export type Release = Shard["releases"][number];
export type Variant = Release["variants"][string];
export type Asset = Variant["binary"];
export type Entry = Release & {
  upstream: string;
  channel: "release" | "master";
  lts: boolean;
};
export type Summary = Pick<
  Entry,
  "tag" | "date" | "upstream" | "channel" | "lts"
> & {
  warning: boolean;
  variants: { key: string; develop: boolean; debug: boolean }[];
};
export const architectures = ["x64", "arm64", "x86", "arm"] as const;
export const linkages = ["shared", "static"] as const;
export const licenses = ["lgpl", "gpl", "nonfree"] as const;
export function variantKey(arch: string, linkage: string, license: string) {
  return arch + "-windows-" + linkage + "-" + license;
}
export function parseVariant(key: string) {
  const [arch, , linkage, license] = key.split("-");
  return { arch, linkage, license };
}
export function assetUrl(repo: string, tag: string, asset: Asset) {
  return (
    repo.replace(/\/+$/, "") +
    "/releases/download/" +
    encodeURIComponent(tag) +
    "/" +
    encodeURIComponent(asset.file)
  );
}
export function formatSize(size: number) {
  return (size / 1048576).toFixed(1) + " MiB";
}
export function compareVersions(a: string, b: string) {
  const aa = a.split(".").map(Number),
    bb = b.split(".").map(Number);
  for (let i = 0; i < Math.max(aa.length, bb.length); i++) {
    const d = (bb[i] ?? 0) - (aa[i] ?? 0);
    if (d) return d;
  }
  return 0;
}
export function compareEntries(
  a: Pick<Entry, "date" | "tag">,
  b: Pick<Entry, "date" | "tag">,
) {
  const revision = (tag: string) =>
    Number(tag.match(/(?:R|-r)(\d+)$/)?.[1] ?? 0);
  return (
    b.date.localeCompare(a.date) ||
    revision(b.tag) - revision(a.tag) ||
    b.tag.localeCompare(a.tag)
  );
}
export function getVariant(
  entry: Entry,
  arch: string,
  linkage: string,
  license: string,
): Variant | undefined {
  return entry.variants[variantKey(arch, linkage, license)];
}
export function legacyId(entry: Entry): string | undefined {
  // A dated release has no corresponding old VitePress route.
  if (/-\d{6}(?:R\d+)?$/.test(entry.tag)) return undefined;
  const revision = entry.tag.match(/(?:R|-r)(\d+)$/)?.[1] ?? "0";
  return (entry.ref ?? "n" + entry.upstream) + "-r" + revision;
}
export function toEntries(shard: Shard, channel: Entry["channel"]): Entry[] {
  return shard.releases
    .map((r) => ({
      ...r,
      upstream: channel === "master" ? r.version! : shard.version!,
      channel,
      lts: shard.lts,
    }))
    .sort(compareEntries);
}
export { localized } from "../i18n/routing";
export function selectVariant(
  keys: readonly string[],
  preferences: { arch: string; linkage: string; license: string },
  changed?: "arch" | "linkage" | "license",
) {
  const choices = keys.map(parseVariant);
  const fields = ["arch", "linkage", "license"] as const;
  const prioritized: (typeof fields)[number][] = changed
    ? [changed, ...fields.filter((f) => f !== changed)]
    : [...fields];
  const score = (v: ReturnType<typeof parseVariant>) =>
    prioritized.reduce<number>(
      (n, f, i) => n + (v[f] === preferences[f] ? 1 << (2 - i) : 0),
      0,
    );
  return (
    choices.sort(
      (a, b) =>
        score(b) - score(a) ||
        architectures.indexOf(a.arch as (typeof architectures)[number]) -
          architectures.indexOf(b.arch as (typeof architectures)[number]) ||
        linkages.indexOf(a.linkage as (typeof linkages)[number]) -
          linkages.indexOf(b.linkage as (typeof linkages)[number]) ||
        licenses.indexOf(a.license as (typeof licenses)[number]) -
          licenses.indexOf(b.license as (typeof licenses)[number]),
    )[0] ?? preferences
  );
}

export type VersionOption = {
  tag: string;
  date: string;
  warning: boolean;
  upstream: string;
  channel: Entry["channel"];
  lts: boolean;
  shard: string;
  keys: string[];
};
export type VersionFilter = "all" | "lts" | "snapshot";

export function majorVersion(version: string) {
  return version.split(".")[0] + ".x";
}
export function releaseSeries(version: string) {
  return version.split(".").slice(0, 2).join(".");
}
export function hasWarning(entry: Pick<Entry, "variants">) {
  return Object.values(entry.variants).some((v) => !!v.note);
}
export function compareOptions(a: VersionOption, b: VersionOption) {
  if (a.channel !== b.channel) return a.channel === "release" ? -1 : 1;
  return (
    (a.channel === "release" ? compareVersions(a.upstream, b.upstream) : 0) ||
    compareEntries(a, b)
  );
}
// Select the latest build of each upstream version before evaluating LTS.
export function versionHeads(options: readonly VersionOption[]) {
  const seen = new Set<string>();
  return [...options].sort(compareOptions).filter((o) => {
    const key = o.channel === "release" ? o.upstream : "master";
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
export function defaultVersionOptions(options: readonly VersionOption[]) {
  const majors = new Set<string>(),
    series = new Set<string>();
  return versionHeads(options).filter((o) => {
    if (o.channel === "master") return true;
    const major = majorVersion(o.upstream),
      branch = releaseSeries(o.upstream);
    const show = !majors.has(major) || (o.lts && !series.has(branch));
    majors.add(major);
    if (o.lts) series.add(branch);
    return show;
  });
}
export function filterVersionOptions(
  options: readonly VersionOption[],
  filter: VersionFilter,
  query: string,
  scope: "picker" | "catalog" = "picker",
) {
  const q = query
    .trim()
    .toLowerCase()
    .replace(/^ffmpeg\s+/, "");
  const eligible = options.filter(
    (o) =>
      (filter !== "lts" || o.lts) &&
      (filter !== "snapshot" || o.channel === "master"),
  );
  // Only the unsearched catalog is aggregated. Explicit catalog queries
  // must not discard matching releases or older build batches.
  const complete = scope === "catalog" && !!q;
  const results = (matched: VersionOption[]) =>
    complete ? [...matched].sort(compareOptions) : versionHeads(matched);
  if (!q || q === "ffmpeg" || q === "lts") {
    const matched = q === "lts" ? eligible.filter((o) => o.lts) : eligible;
    return complete ? results(matched) : defaultVersionOptions(matched);
  }
  if (/^\d+(?:\.x)?$/.test(q)) {
    const major = q.replace(/\.x$/, "") + ".x";
    const matched = eligible.filter((o) => majorVersion(o.upstream) === major);
    return complete ? results(matched) : defaultVersionOptions(matched);
  }
  const exact = eligible.find((o) => o.tag.toLowerCase() === q);
  if (exact) return [exact];
  if (/^\d+\.\d+(?:\.\d+)?$/.test(q)) {
    return results(
      eligible.filter(
        (o) =>
          o.upstream === q ||
          (q.split(".").length === 2 && o.upstream.startsWith(q + ".")) ||
          (o.channel === "master" && o.upstream.startsWith(q + "-")),
      ),
    );
  }
  const terms = q.split(/\s+/);
  const matched = eligible.filter((o) => {
    const search = [
      o.upstream,
      o.tag,
      o.channel === "master"
        ? "master development dev snapshot snapshots 开发版 开发版本 快照"
        : "ffmpeg release releases stable versions all versions 稳定版本 全部版本 历史版本",
      o.lts ? "lts" : "",
    ]
      .join(" ")
      .toLowerCase();
    return terms.every((term) => search.includes(term));
  });
  return results(matched);
}
