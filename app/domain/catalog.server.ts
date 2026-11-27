import { readFileSync } from "node:fs";
import type { Index, Shard, Entry, Summary } from "./catalog";
import {
  compareVersions,
  legacyId,
  toEntries,
  hasWarning,
  defaultVersionOptions,
  majorVersion,
  type VersionOption,
} from "./catalog";
import { repo } from "../../scripts/site-config";
type Snapshot = { index: Index; shards: Record<string, Shard> };
let snapshot: Snapshot | undefined;
function load() {
  return (snapshot ??= JSON.parse(
    readFileSync(".generated/catalog.json", "utf8"),
  ) as Snapshot);
}
export function entries(key: string): Entry[] {
  const shard = load().shards[key];
  if (!shard) return [];
  return toEntries(shard, key.startsWith("master/") ? "master" : "release");
}
export function allEntries() {
  return Object.keys(load().shards).flatMap(entries);
}
export function catalogSummary() {
  const { index } = load();
  return {
    releases: [...index.releases].sort(compareVersions).map((version) => ({
      version,
      lts: load().shards["releases/" + version].lts,
      records: entries("releases/" + version).map(summary),
    })),
    master: [...index.master]
      .sort((a, b) => b - a)
      .map((year) => ({
        year,
        records: entries("master/" + year).map(summary),
      })),
    repo,
  };
}
function summary(e: Entry): Summary {
  return {
    tag: e.tag,
    date: e.date,
    upstream: e.upstream,
    channel: e.channel,
    lts: e.lts,
    warning: hasWarning(e),
    variants: Object.entries(e.variants).map(([key, value]) => ({
      key,
      develop: !!value.develop,
      debug: !!value.debug,
    })),
  };
}
export function searchOptions(): VersionOption[] {
  return allEntries().map((e) => ({
    tag: e.tag,
    date: e.date,
    upstream: e.upstream,
    channel: e.channel,
    lts: e.lts,
    warning: hasWarning(e),
    shard:
      e.channel === "release"
        ? "releases/" + e.upstream
        : "master/" + e.date.slice(0, 4),
    keys: Object.keys(e.variants),
  }));
}
export function latest() {
  const search = searchOptions();
  const options = defaultVersionOptions(search);
  const initial = options[0]
    ? entries(options[0].shard).find((e) => e.tag === options[0].tag)
    : undefined;
  return { options, search, initial, repo };
}
export function majorEntries(major: string) {
  return catalogSummary().releases.filter(
    (v) => majorVersion(v.version) === major,
  );
}
export function findBuild(tag: string) {
  return allEntries().find((e) => e.tag === tag || legacyId(e) === tag);
}
export { repo };
