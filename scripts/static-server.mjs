import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { resolve, extname, sep } from "node:path";
const base = process.env.BASE_URL ?? "/";
const root = resolve(process.env.PREVIEW_ROOT ?? "build/client");
const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".data": "text/x-script",
  ".xml": "application/xml",
};
createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (base !== "/" && url.pathname === base.slice(0, -1)) {
    res.writeHead(301, { Location: base + url.search }).end();
    return;
  }
  if (!url.pathname.startsWith(base)) {
    res.writeHead(404).end();
    return;
  }
  try {
    let file = resolve(
      root,
      decodeURIComponent(url.pathname.slice(base.length)),
    );
    if (file !== root && !file.startsWith(root + sep)) {
      res.writeHead(403).end();
      return;
    }
    if ((await stat(file)).isDirectory()) {
      if (!url.pathname.endsWith("/")) {
        res.writeHead(301, { Location: url.pathname + "/" + url.search }).end();
        return;
      }
      file = resolve(file, "index.html");
    }
    const content = await readFile(file);
    res
      .writeHead(200, {
        "Content-Type": mime[extname(file)] ?? "application/octet-stream",
      })
      .end(content);
  } catch {
    res
      .writeHead(404, { "Content-Type": "text/html" })
      .end(
        await readFile(resolve(root, "404.html")).catch(() =>
          Buffer.from("Not found"),
        ),
      );
  }
}).listen(Number(process.env.PORT ?? 4173), "127.0.0.1");
