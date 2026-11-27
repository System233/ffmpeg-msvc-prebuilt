import type { Config } from "@react-router/dev/config";
import { readFileSync } from "node:fs";
import {
  enumerateRoutes,
  enumerateLocalizedPages,
} from "./scripts/static-routes";
import { base } from "./scripts/site-config";
export default {
  ssr: false,
  buildDirectory: process.env.BUILD_DIR ?? "build",
  future: { v8_trailingSlashAwareDataRequests: true },
  basename: base,
  async prerender() {
    const { index, shards } = JSON.parse(
      readFileSync(".generated/catalog.json", "utf8"),
    );
    return enumerateLocalizedPages(enumerateRoutes(index, shards));
  },
} satisfies Config;
