import type { Config } from "@react-router/dev/config";
import { readFileSync } from "node:fs";
import { base } from "./scripts/site-config";
export default {
  ssr: false,
  buildDirectory: process.env.BUILD_DIR ?? "build",
  future: { v8_trailingSlashAwareDataRequests: true },
  basename: base === "/" ? "/" : base.slice(0, -1),
  async prerender() {
    const { index, shards } = JSON.parse(
      readFileSync(".generated/catalog.json", "utf8"),
    );
    const paths = [
      "/",
      "/releases/",
      "/master/",
      "/guide/",
      "/integration/",
      "/packages/",
      "/licenses/",
      "/reference/",
      "/self-build/",
      "/history/",
      ...index.releases.map((v: string) => "/releases/" + v + "/"),
      ...index.master.map((y: number) => "/master/" + y + "/"),
      ...Object.values(shards).flatMap((s: any) =>
        s.releases.map((r: any) => "/build/" + r.tag + "/"),
      ),
    ];
    return [
      ...new Set([
        "/",
        ...["en", "zh"].flatMap((lang) => paths.map((p) => "/" + lang + p)),
        ...paths,
      ]),
    ];
  },
} satisfies Config;
