import { readFileSync, readdirSync, statSync } from "node:fs";
import { resolve, join } from "node:path";
import { gzipSync } from "node:zlib";
const root = resolve("build/client");
const html = readFileSync(join(root, "index.html"));
const data = readFileSync(join(root, "_.data"));
const js = [
  ...new Set(
    [
      ...html.toString().matchAll(/(?:src|href)="[^"]*\/assets\/([^"]+\.js)"/g),
    ].map((m) => m[1]),
  ),
];
const jsGzip = js.reduce(
  (n, f) => n + gzipSync(readFileSync(join(root, "assets", f))).length,
  0,
);
function files(path: string): string[] {
  return readdirSync(path, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? files(join(path, e.name)) : [join(path, e.name)],
  );
}
const all = files(root);
console.log(
  JSON.stringify(
    {
      homeHtmlBytes: html.length,
      homeHtmlGzipBytes: gzipSync(html).length,
      homeDataBytes: data.length,
      homeDataGzipBytes: gzipSync(data).length,
      initialJsGzipBytes: jsGzip,
      siteBytes: all.reduce((n, f) => n + statSync(f).size, 0),
      fileCount: all.length,
    },
    null,
    2,
  ),
);
