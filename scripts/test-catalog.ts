// Deterministic synthetic data for the native dated-format and sparse-matrix regression.
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import type { Index, Shard, Variant } from "../app/domain/catalog";
const root = ".generated/fixture-data";
rmSync(root, { force: true, recursive: true });
mkdirSync(root + "/releases", { recursive: true });
mkdirSync(root + "/master", { recursive: true });
const index: Index = {
  schema: 1,
  releases: ["9.1", "9.0.2", "8.1.3"],
  master: [2026],
};
const asset = (file: string, size = 1048576) => ({
  file,
  size,
  sha256: createHash("sha256").update(file).digest("hex"),
});
function native(
  version: string,
  key: string,
  date = "261125",
  reuse = false,
): Variant {
  const stem = "ffmpeg-" + version + "_" + key;
  return {
    abi: "b".repeat(64),
    format: 2,
    ...(reuse ? { date: "2026-11-24" } : {}),
    binary: asset(stem + "-" + date + ".zip"),
    ...(key.includes("-shared-")
      ? { debug: asset(stem + "-debug-" + date + ".zip", 2097152) }
      : {}),
  };
}
const latest = {
  "x64-windows-shared-lgpl": native("9.1", "x64-windows-shared-lgpl"),
  "arm64-windows-static-gpl": native(
    "9.1",
    "arm64-windows-static-gpl",
    "261124",
    true,
  ),
  "x64-windows-shared-nonfree": native("9.1", "x64-windows-shared-nonfree"),
};
const previous = {
  "x64-windows-shared-lgpl": native(
    "9.1",
    "x64-windows-shared-lgpl",
    "261125",
    false,
  ),
};
const full = Object.fromEntries(
  ["x64", "arm64", "x86", "arm"].flatMap((a) =>
    ["shared", "static"].flatMap((l) =>
      ["lgpl", "gpl"].map((p) => {
        const key = a + "-windows-" + l + "-" + p;
        return [key, native("9.0.2", key)];
      }),
    ),
  ),
);
const shards: Record<string, Shard> = {
  "releases/9.0.2": {
    version: "9.0.2",
    lts: true,
    releases: [
      { tag: "ffmpeg-9.0.2-261125", date: "2026-11-25", variants: full },
    ],
  },
  "releases/9.1": {
    version: "9.1",
    lts: false,
    releases: [
      { tag: "ffmpeg-9.1-261125R2", date: "2026-11-25", variants: previous },
      { tag: "ffmpeg-9.1-261125R10", date: "2026-11-25", variants: latest },
      {
        tag: "ffmpeg-9.1-261125",
        date: "2026-11-25",
        variants: {
          "x64-windows-shared-lgpl": native(
            "9.1",
            "x64-windows-shared-lgpl",
            "261125",
            false,
          ),
        },
      },
    ],
  },
  "releases/8.1.3": {
    version: "8.1.3",
    lts: false,
    releases: [
      {
        tag: "ffmpeg-8.1.3-r1",
        date: "2026-09-21",
        variants: {
          "x86-windows-shared-lgpl": {
            note: "legacy-lgpl-licensing",
            binary: asset("ffmpeg-8.1.3-r1_x86-windows-shared-lgpl.zip"),
            develop: asset(
              "ffmpeg-8.1.3-r1_x86-windows-shared-lgpl-develop.zip",
            ),
          },
          "x86-windows-shared-gpl": {
            binary: asset("ffmpeg-8.1.3-r1_x86-windows-shared-gpl.zip"),
            develop: asset(
              "ffmpeg-8.1.3-r1_x86-windows-shared-gpl-develop.zip",
            ),
          },
        },
      },
    ],
  },
  "master/2026": {
    year: 2026,
    lts: false,
    releases: [
      {
        version: "9.2-dev-100-g1234567",
        commit: "1".repeat(40),
        tag: "ffmpeg-master-261125R2",
        date: "2026-11-25",
        variants: {
          "x64-windows-shared-lgpl": native(
            "master",
            "x64-windows-shared-lgpl",
          ),
        },
      },
      {
        version: "9.2-dev-100-g1234567",
        commit: "1".repeat(40),
        tag: "ffmpeg-master-261125R10",
        date: "2026-11-25",
        variants: {
          "x64-windows-shared-lgpl": native(
            "master",
            "x64-windows-shared-lgpl",
          ),
        },
      },
    ],
  },
};
writeFileSync(root + "/index.json", JSON.stringify(index));
for (const [key, value] of Object.entries(shards))
  writeFileSync(root + "/" + key + ".json", JSON.stringify(value));
console.log("Synthetic fixture ready: 7 releases (not production assets).");
