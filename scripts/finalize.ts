import {
  readFileSync,
  writeFileSync,
  existsSync,
  mkdirSync,
  cpSync,
  rmSync,
} from "node:fs";
import { resolve } from "node:path";
import { base, siteUrl } from "./site-config";
import { enumerateRoutes, enumerateLocalizedPages } from "./static-routes";
import { localized } from "../app/i18n/routing";
import { t } from "../app/i18n";
import { errorPage } from "./error-page";
import {
  legacyId,
  majorVersion,
  compareVersions,
  toEntries,
  type Index,
  type Shard,
} from "../app/domain/catalog";
const dir = resolve(process.env.BUILD_DIR ?? "build", "client");
if (base !== "/") {
  const nested = resolve(dir, "." + base);
  cpSync(nested, dir, { recursive: true });
  rmSync(nested, { recursive: true, force: true });
}
const { index, shards } = JSON.parse(
  readFileSync(".generated/catalog.json", "utf8"),
) as { index: Index; shards: Record<string, Shard> };
const paths = enumerateRoutes(index, shards);
const all = enumerateLocalizedPages(paths);
for (const p of all) {
  if (!existsSync(resolve(dir, "." + p, "index.html")))
    throw Error("Missing prerendered page " + p);
  if (!existsSync(resolve(dir, "." + p, "_.data")))
    throw Error("Missing static route data " + p);
}
rmSync(resolve(dir, "__spa-fallback.html"), { force: true });
writeFileSync(resolve(dir, ".nojekyll"), "");
const stylesheets = [
  ...readFileSync(resolve(dir, "index.html"), "utf8").matchAll(
    /<link\b[^>]*rel="stylesheet"[^>]*href="([^"]+)"[^>]*>/g,
  ),
].map((m) => m[1]);
if (
  !stylesheets.length ||
  stylesheets.some(
    (href) =>
      !href.startsWith(base) ||
      !existsSync(resolve(dir, href.slice(base.length))),
  )
) {
  throw Error("Missing stylesheet for static error page");
}
writeFileSync(resolve(dir, "404.html"), errorPage(stylesheets));
writeFileSync(
  resolve(dir, "sitemap.xml"),
  '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
    all.map((p) => "<url><loc>" + siteUrl + p + "</loc></url>").join("") +
    "</urlset>",
);
writeFileSync(
  resolve(dir, "robots.txt"),
  "User-agent: *\nAllow: /\nSitemap: " + siteUrl + "/sitemap.xml\n",
);
const redirects = new Map<string, string>();
function redirect(oldPath: string, newPath: string, script = "") {
  const existing = redirects.get(oldPath);
  if (existing && existing !== newPath)
    throw Error("Ambiguous legacy path " + oldPath);
  redirects.set(oldPath, newPath);
  const path = resolve(dir, "." + oldPath);
  mkdirSync(resolve(path, ".."), { recursive: true });
  writeFileSync(
    path,
    '<!doctype html><html><meta charset="utf-8">' +
      (script ||
        "<script>location.replace(" +
          JSON.stringify(base + newPath.slice(1)).replace(/</g, "\\u003c") +
          "+location.search+location.hash)</script>") +
      '<meta http-equiv="refresh" content="0;url=' +
      base +
      newPath.slice(1) +
      '"><link rel="canonical" href="' +
      siteUrl +
      newPath +
      '"><a href="' +
      base +
      newPath.slice(1) +
      '">' +
      t(newPath.startsWith("/zh/") ? "zh" : "en", "common.continue") +
      "</a></html>",
  );
}
for (const p of paths) redirect("/en" + p + "index.html", p);
for (const l of ["en", "zh"]) {
  for (const p of paths.filter((p) => p !== "/" && !p.startsWith("/build/")))
    redirect("/" + l + p.slice(0, -1) + ".html", localized(l, p));
  for (const [key, s] of Object.entries(shards)) {
    for (const entry of toEntries(
      s,
      key.startsWith("master/") ? "master" : "release",
    )) {
      const id = legacyId(entry);
      if (id)
        redirect(
          "/" + l + "/releases/" + id + ".html",
          localized(l, "/build/" + entry.tag + "/"),
        );
    }
  }
}
// Former major detail URLs are compatibility redirects, not catalog pages.
for (const major of new Set(index.releases.map(majorVersion))) {
  const versions = index.releases
    .filter((v) => majorVersion(v) === major)
    .sort(compareVersions);
  for (const lang of ["", "/en", "/zh"]) {
    const prefix = lang === "/zh" ? "/zh" : "";
    const target = prefix + "/releases/" + versions[0] + "/";
    const byTag = Object.fromEntries(
      versions.flatMap((v) =>
        toEntries(shards["releases/" + v], "release").map((entry, i) => [
          entry.tag,
          prefix +
            (i === 0 ? "/releases/" + v + "/" : "/build/" + entry.tag + "/"),
        ]),
      ),
    );
    const js =
      "<script>(()=>{const p=new URLSearchParams(location.search), tag=p.get('version');p.delete('version');const targets=" +
      JSON.stringify(byTag).replace(/</g, "\\u003c") +
      ";let path=" +
      JSON.stringify(target) +
      ";if(tag){if(Object.hasOwn(targets,tag))path=targets[tag];else{path=" +
      JSON.stringify(prefix + "/releases/") +
      ";p.set('q',tag)}}location.replace(" +
      JSON.stringify(base) +
      "+path.slice(1)+(p.size?'?'+p.toString():'')+location.hash)})()</script>";
    redirect(lang + "/releases/" + major + "/index.html", target, js);
    if (lang) redirect(lang + "/releases/" + major + ".html", target, js);
  }
}
console.log(
  "Verified " +
    all.length +
    " static pages and route data files; generated " +
    redirects.size +
    " legacy redirects",
);
