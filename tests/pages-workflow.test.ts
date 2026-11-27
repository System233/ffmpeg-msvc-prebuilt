import { readFileSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { spawnSync } from "node:child_process";
import { describe, it, expect } from "vitest";

const workflow = readFileSync(".github/workflows/pages.yml", "utf8");

describe("Pages release catalog workflow", () => {
  it("validates data before building and uploads only the current site", () => {
    expect(workflow).toContain("sparse-checkout: schema");
    expect(workflow).toContain("pnpm prepareData");
    expect(workflow).toContain("path: web/build/client");
    expect(workflow).not.toMatch(
      /catalogSchema|steps\.contract|\.vitepress\/dist|Build legacy/,
    );
  });
});

describe("Release catalog validation", () => {
  it.each([
    ["missing index", undefined],
    ["corrupt JSON", "not JSON"],
    ["unsupported schema", '{"schema":2,"releases":[],"master":[]}'],
    ["missing shard", '{"schema":1,"releases":["9.1"],"master":[]}'],
  ])("rejects %s before publication", (_name, index) => {
    const root = mkdtempSync(join(tmpdir(), "catalog-validation-"));
    try {
      if (index !== undefined) writeFileSync(join(root, "index.json"), index);
      const result = spawnSync(
        process.execPath,
        ["--import", "tsx", "scripts/prepare-data.ts"],
        {
          encoding: "utf8",
          env: {
            ...process.env,
            CATALOG_DIR: root,
            SCHEMA_DIR: resolve(process.env.SCHEMA_DIR ?? "schema"),
          },
        },
      );
      expect(result.status).not.toBe(0);
      // A child process that cannot start is not a successful rejection.
      expect(result.error).toBeUndefined();
      expect(result.stderr).toMatch(
        /index\.json|SyntaxError|Invalid catalog|releases[\\/]9\.1\.json/,
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
