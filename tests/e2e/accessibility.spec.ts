import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { allEntries } from "../../app/domain/catalog.server";
const entry = allEntries()[0];
for (const [name, path] of [
  ["home", ""],
  ["list", "releases/"],
  ["detail", "build/" + entry.tag + "/"],
  ["guide", "zh/guide/"],
  ["integration", "zh/integration/"],
  ["packages", "zh/packages/"],
  ["licenses", "zh/licenses/"],
  ["404 English", "not-a-valid-page/"],
  ["404 Chinese", "zh/not-a-valid-page/"],
]) {
  test("WCAG A/AA: " + name, async ({ page }) => {
    await page.goto("./" + path);
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(
      result.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
    ).toEqual([]);
  });
}
