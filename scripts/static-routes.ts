import { documentPages } from "../app/content/config";
import type { Index, Shard } from "../app/domain/catalog";
import { languages } from "../app/i18n/config";
import { localized } from "../app/i18n/routing";
export function enumerateRoutes(index: Index, shards: Record<string, Shard>) {
  return [
    ...new Set([
      "/",
      "/releases/",
      "/master/",
      ...documentPages.map(([path]) => "/" + path + "/"),
      ...index.releases.map((v) => "/releases/" + v + "/"),
      ...index.master.map((y) => "/master/" + y + "/"),
      ...Object.values(shards).flatMap((s) =>
        s.releases.map((r) => "/build/" + r.tag + "/"),
      ),
    ]),
  ];
}
export function enumerateLocalizedPages(paths: string[]) {
  return languages.flatMap((lang) =>
    paths.map((path) => localized(lang, path)),
  );
}
