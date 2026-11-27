import { packageNote } from "../app/lib/asset-copy";
import { describe, it, expect } from "vitest";
import { describeAssets, validAssetSet } from "../app/domain/assets";
import {
  compareVersions,
  defaultVersionOptions,
  type VersionOption,
  filterVersionOptions,
  compareEntries,
  variantKey,
  parseVariant,
  getVariant,
  assetUrl,
  formatSize,
  legacyId,
  selectVariant,
  type Entry,
  type Variant,
} from "../app/domain/catalog";
import {
  allEntries,
  catalogSummary,
  latest,
} from "../app/domain/catalog.server";
describe("catalog domain", () => {
  const entries = allEntries();
  it("distinguishes historical standalone Develop from Debug add-on", () => {
    const binary = { file: "binary.zip", size: 1, sha256: "a".repeat(64) };
    expect(
      describeAssets(
        {
          binary,
          debug: { ...binary, file: "debug.zip" },
          format: 2,
          abi: "b".repeat(64),
        },
        "shared",
      )[1],
    ).toMatchObject({ kind: "debug", requiresBinary: true });
    expect(
      describeAssets(
        { binary, develop: { ...binary, file: "develop.zip" } },
        "shared",
      )[1],
    ).toMatchObject({ kind: "develop", requiresBinary: false });
    expect(describeAssets({ binary }, "static")).toHaveLength(1);
  });
  it("sorts numeric versions", () =>
    expect(["9.1", "9.0.2", "10.0", "9.0.10"].sort(compareVersions)).toEqual([
      "10.0",
      "9.1",
      "9.0.10",
      "9.0.2",
    ]));
  it("maps every indexed tag exactly once", () =>
    expect(new Set(entries.map((e) => e.tag)).size).toBe(entries.length));
  it("separates stable and master records", () => {
    const s = catalogSummary();
    expect(
      s.releases
        .flatMap((x) => x.records)
        .every((x) => x.channel === "release"),
    ).toBe(true);
    expect(
      s.master.flatMap((x) => x.records).every((x) => x.channel === "master"),
    ).toBe(true);
  });
  it("round-trips every variant and checks every downloadable asset", () => {
    for (const entry of entries)
      for (const [key, v] of Object.entries(entry.variants)) {
        const { arch, linkage, license } = parseVariant(key);
        expect(variantKey(arch, linkage, license)).toBe(key);
        expect(getVariant(entry, arch, linkage, license)).toEqual(v);
        for (const a of [v.binary, v.develop, v.debug].filter(Boolean)) {
          expect(a!.sha256).toMatch(/^[0-9a-f]{64}$/);
          expect(
            assetUrl(
              "https://github.com/System233/ffmpeg-msvc-prebuilt",
              entry.tag,
              a!,
            ),
          ).toContain("/releases/download/" + entry.tag + "/" + a!.file);
          expect(a!.size).toBeGreaterThan(0);
        }
      }
  });
  it("sorts same-day rebuild revisions numerically", () => {
    const entry = entries[0];
    expect(
      [
        { ...entry, tag: "ffmpeg-9.1-r2" },
        { ...entry, tag: "ffmpeg-9.1-r10" },
      ].sort(compareEntries)[0].tag,
    ).toBe("ffmpeg-9.1-r10");
  });
  it("sorts native same-day batches numerically", () => {
    const e = entries[0];
    const rows = [
      { ...e, tag: "ffmpeg-9.1-261125R2" },
      { ...e, tag: "ffmpeg-9.1-261125R10" },
      { ...e, tag: "ffmpeg-9.1-261125" },
    ];
    expect(rows.sort(compareEntries)[0].tag).toBe("ffmpeg-9.1-261125R10");
    expect(legacyId(rows[0])).toBeUndefined();
  });
  it("selects a valid sparse variant while honoring the changed dimension", () => {
    const keys = ["x64-windows-shared-lgpl", "arm64-windows-static-gpl"];
    expect(
      selectVariant(
        keys,
        { arch: "arm64", linkage: "shared", license: "lgpl" },
        "arch",
      ),
    ).toEqual({ arch: "arm64", linkage: "static", license: "gpl" });
  });
  it("formats MiB", () => expect(formatSize(1048576)).toBe("1.0 MiB"));
  it("keeps missing combinations absent", () =>
    expect(getVariant(entries[0], "invalid", "shared", "gpl")).toBeUndefined());
});

describe("asset set validation", () => {
  const binary = { file: "binary.zip", size: 1, sha256: "a".repeat(64) },
    develop = { ...binary, file: "develop.zip" },
    debug = { ...binary, file: "debug.zip" };
  const native = { binary, abi: "b".repeat(64) };
  it("requires exactly the expected artifacts for the native format", () => {
    expect(validAssetSet({ binary, develop }, "shared")).toBe(true);
    expect(validAssetSet({ ...native, format: 2, debug }, "shared")).toBe(true);
    expect(validAssetSet({ ...native, format: 2 }, "static")).toBe(true);
    for (const v of [
      { ...native, format: 2 as const, develop },
      { ...native, format: 2 as const },
      { ...native, debug },
      { ...native, format: 2 as const, debug, develop },
      { binary, debug },
    ])
      expect(validAssetSet(v, "shared")).toBe(false);
    for (const format of [1, 3, 4, 99]) {
      expect(
        validAssetSet(
          { ...native, format, debug } as unknown as Variant,
          "shared",
        ),
      ).toBe(false);
    }
    expect(validAssetSet({ ...native, format: 2, debug }, "static")).toBe(
      false,
    );
  });
  it("identifies primary package purpose without altering its identity", () => {
    expect(
      describeAssets({ ...native, format: 2, debug }, "shared").map(
        (a) => a.role,
      ),
    ).toEqual(["release-sdk", "debug-addon"]);
    expect(
      describeAssets({ binary, develop }, "shared").map((a) => a.role),
    ).toEqual(["release-sdk", "legacy-sdk"]);
    expect(describeAssets({ binary }, "static")[0].asset).toBe(binary);
  });
});

describe("package note coverage", () => {
  it("explains every actual package type without historical qualifiers", () => {
    for (const entry of allEntries()) {
      for (const [key, v] of Object.entries(entry.variants)) {
        const assets = describeAssets(v, key.split("-")[2]);
        for (const lang of ["en", "zh"] as const) {
          const note = packageNote(assets, lang)!;
          expect(note).toContain(lang === "zh" ? "二进制" : "Binary");
          expect(note.includes(lang === "zh" ? "开发版" : "Develop")).toBe(
            !!v.develop,
          );
          expect(note.includes(lang === "zh" ? "调试库 " : "Debug")).toBe(
            !!v.debug,
          );
          expect(note.split(lang === "zh" ? "；" : "; ")).toHaveLength(
            assets.length,
          );
          expect(note).not.toMatch(/historical|历史|[:：•]|可独立使用/i);
        }
      }
    }
  });
});

describe("explicit LTS metadata", () => {
  it("uses the catalog flag and never infers it from version numbers", () => {
    const { options } = latest();
    const snapshots = filterVersionOptions(options, "snapshot", "");
    expect(snapshots.length).toBeGreaterThan(0);
    expect(snapshots.every((o) => o.channel === "master" && !o.lts)).toBe(true);
    const lts = filterVersionOptions(options, "lts", "");
    expect(lts).toEqual(options.filter((o) => o.lts));
    expect(filterVersionOptions(options, "all", "LTS")).toEqual(lts);
    expect(filterVersionOptions(options, "all", "no-such-version")).toEqual([]);
    expect(filterVersionOptions(options, "snapshot", "快照")).toEqual(
      snapshots,
    );
    const sample = options.find((o) => o.channel === "release")!;
    const explicitlyMarked = { ...sample, upstream: "8.0", lts: true };
    const explicitlyUnmarked = { ...sample, upstream: "7.1", lts: false };
    expect(
      filterVersionOptions([explicitlyMarked, explicitlyUnmarked], "lts", ""),
    ).toEqual([explicitlyMarked]);
  });
  it("preserves LTS metadata in summaries and entries", () => {
    const s = catalogSummary();
    for (const family of s.releases) {
      expect(typeof family.lts).toBe("boolean");
      expect(family.records.every((r) => r.lts === family.lts)).toBe(true);
    }
    expect(
      allEntries()
        .filter((e) => e.channel === "master")
        .every((e) => e.lts === false),
    ).toBe(true);
  });
});

it("only historical LGPL variants carry the licensing notice", () => {
  let count = 0;
  for (const entry of allEntries()) {
    for (const [slot, variant] of Object.entries(entry.variants)) {
      if (slot.endsWith("-lgpl") && !variant.abi) {
        expect(variant.note).toBe("legacy-lgpl-licensing");
        count++;
      } else {
        expect(variant.note).toBeUndefined();
      }
    }
  }
  expect(count).toBeGreaterThan(0);
});

describe("major and maintenance series visibility", () => {
  const row = (
    upstream: string,
    lts: boolean,
    revision = 0,
    warning = false,
    date = "2026-11-27",
  ): VersionOption => ({
    upstream,
    lts,
    date,
    warning,
    channel: "release",
    tag: "ffmpeg-" + upstream + "-261127" + (revision ? "R" + revision : ""),
    shard: "releases/" + upstream,
    keys: ["x64-windows-shared-lgpl"],
  });
  const latest = row("9.2", false),
    lts = row("9.1.5", true),
    prior = row("9.1.4", true, 0, true);
  const old = row("9.0.2", false, 0, true),
    other = row("8.1.3", false, 0, true);
  const dataset = [prior, old, lts, other, latest];
  it("shows current and separate LTS series, not obsolete patches", () => {
    expect(defaultVersionOptions(dataset)).toEqual([latest, lts, other]);
    expect(filterVersionOptions(dataset, "lts", "")).toEqual([lts]);
    expect(filterVersionOptions(dataset, "all", "9.x")).toEqual([latest, lts]);
    expect(filterVersionOptions(dataset, "all", "9.1")).toEqual([lts, prior]);
    expect(filterVersionOptions(dataset, "all", "9.1.4")).toEqual([prior]);
    expect(filterVersionOptions(dataset, "all", "9.0.2")).toEqual([old]);
  });
  it("searches all matching catalog releases and batches without changing picker defaults", () => {
    const earlier = row("9.2", false, 2, true);
    const newer = row("9.2", false, 10);
    const all = [earlier, newer, ...dataset.filter((o) => o !== latest)];
    const matches = [newer, earlier, lts, prior, old];
    expect(filterVersionOptions(all, "all", "", "catalog")).toEqual([
      newer,
      lts,
      other,
    ]);
    expect(filterVersionOptions(all, "all", "9", "catalog")).toEqual(matches);
    expect(filterVersionOptions(all, "all", "9.x", "catalog")).toEqual(matches);
    expect(filterVersionOptions(all, "all", "FFmpeg 9.x", "catalog")).toEqual(
      matches,
    );
    expect(filterVersionOptions(all, "all", "9.2", "catalog")).toEqual([
      newer,
      earlier,
    ]);
    expect(
      filterVersionOptions(all, "all", "ffmpeg-9.2-261127r", "catalog"),
    ).toEqual([newer, earlier]);
    expect(filterVersionOptions(all, "all", earlier.tag, "catalog")).toEqual([
      earlier,
    ]);
    expect(filterVersionOptions(all, "lts", "9", "catalog")).toEqual([
      lts,
      prior,
    ]);
    expect(filterVersionOptions(all, "all", "LTS", "catalog")).toEqual([
      lts,
      prior,
    ]);
    expect(filterVersionOptions(all, "all", "ffmpeg", "catalog")).toEqual([
      ...matches,
      other,
    ]);
    expect(filterVersionOptions(all, "all", "9.x")).toEqual([newer, lts]);
  });
  it("advances Latest and LTS independently and deduplicates a shared head", () => {
    const next = row("9.3", false),
      nextLts = row("9.1.6", true);
    expect(defaultVersionOptions([...dataset, nextLts, next])).toEqual([
      next,
      nextLts,
      other,
    ]);
    expect(defaultVersionOptions([lts, prior, other])).toEqual([lts, other]);
    const secondLts = row("9.0.3", true);
    expect(defaultVersionOptions([...dataset, secondLts])).toEqual([
      latest,
      lts,
      secondLts,
      other,
    ]);
  });
  it("keeps an older warning only on its exact build and never mixes variant slots", () => {
    const previous = row("9.2", false, 2, true);
    const next = {
      ...row("9.2", false, 10),
      keys: ["arm64-windows-static-gpl"],
    };
    const builds = [previous, next, ...dataset];
    expect(defaultVersionOptions(builds)[0]).toEqual(next);
    expect(filterVersionOptions(builds, "all", previous.tag)).toEqual([
      previous,
    ]);
    expect(filterVersionOptions(builds, "all", "9.2")).toEqual([next]);
    expect(next.warning).toBe(false);
    expect(previous.warning).toBe(true);
    expect(next.keys).toEqual(["arm64-windows-static-gpl"]);
  });
  it("does not sort lower upstream branches ahead by build date", () => {
    const lower = row("9.1.6", true, 10, false, "2026-11-28");
    expect(defaultVersionOptions([lower, latest])[0]).toEqual(latest);
    expect(
      filterVersionOptions([row("9.10", false), lts, prior], "all", "9.1"),
    ).toEqual([lts, prior]);
  });
});
