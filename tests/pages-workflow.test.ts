import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { describe, it, expect } from "vitest";
const yaml = readFileSync(".github/workflows/pages.yml", "utf8");
const source = yaml.match(
  /node --input-type=module <<'JS'\r?\n([\s\S]*?)\r?\n\s+JS/,
)?.[1];
if (!source) throw Error("Missing workflow contract gate");
function gate(frontendV2: boolean, index: unknown, raw = false, legacy = true) {
  const root = mkdtempSync(join(tmpdir(), "pages-gate-"));
  try {
    mkdirSync(join(root, "web", "data"), { recursive: true });
    writeFileSync(
      join(root, "web", "package.json"),
      JSON.stringify(frontendV2 ? { config: { catalogSchema: 2 } } : {}),
    );
    if (index !== undefined)
      writeFileSync(
        join(root, "web", "data", "index.json"),
        raw ? String(index) : JSON.stringify(index),
      );
    if (index === undefined && legacy)
      mkdirSync(join(root, "web", "data", "9.x"));
    const output = join(root, "output"),
      summary = join(root, "summary");
    const r = spawnSync(
      process.execPath,
      ["--input-type=module", "-e", source!],
      {
        cwd: root,
        encoding: "utf8",
        env: {
          ...process.env,
          GITHUB_OUTPUT: output,
          GITHUB_STEP_SUMMARY: summary,
        },
      },
    );
    return {
      code: r.status,
      output: r.status === 0 ? readFileSync(output, "utf8") : "",
      stdout: r.stdout,
    };
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}
describe("Pages cutover contract gate", () => {
  it("allows the old site with legacy data", () =>
    expect(gate(false, undefined).output).toBe(
      "compatible=true\nmode=legacy\n",
    ));
  it("allows the new site with V2 data", () =>
    expect(gate(true, { schema: 2 }).output).toBe(
      "compatible=true\nmode=v2\n",
    ));
  it("preserves deployed site if data is migrated first", () =>
    expect(gate(false, { schema: 2 }).output).toBe(
      "compatible=false\nmode=legacy\n",
    ));
  it("preserves deployed site if web is switched first", () =>
    expect(gate(true, undefined).output).toBe("compatible=false\nmode=v2\n"));
  it("rejects unsupported data schema instead of falling back", () =>
    expect(gate(false, { schema: 3 }).code).not.toBe(0));
  it("rejects missing catalog", () =>
    expect(gate(false, undefined, false, false).code).not.toBe(0));
  it("rejects corrupt data instead of falling back", () =>
    expect(gate(true, "invalid json", true).code).not.toBe(0));
});
