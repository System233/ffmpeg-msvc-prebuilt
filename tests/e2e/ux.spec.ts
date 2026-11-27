import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { allEntries } from "../../app/domain/catalog.server";
const entry = allEntries().find((e) => e.channel === "release")!;
const detail = "./build/" + entry.tag + "/";
for (const width of [1440, 1024, 820, 390, 320]) {
  test("stable matrix and no overflow at " + width, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(detail);
    const trigger = page.locator(".matrix-row:visible .info-trigger").first();
    const metrics = () =>
      page.locator(".build-matrix").evaluate((el) => ({
        width: el.getBoundingClientRect().width,
        height: el.getBoundingClientRect().height,
        top: el.getBoundingClientRect().top,
        scroll: window.scrollY,
        pageWidth: document.documentElement.scrollWidth,
        viewport: document.documentElement.clientWidth,
        cells: [...el.querySelectorAll(".matrix-cell")].map((x) => {
          const r = x.getBoundingClientRect();
          return [r.x, r.y, r.width, r.height];
        }),
      }));
    await trigger.scrollIntoViewIfNeeded();
    const before = await metrics();
    expect(before.pageWidth).toBeLessThanOrEqual(before.viewport);
    await trigger.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("SHA-256", { exact: true })).toBeVisible();
    expect(await metrics()).toEqual(before);
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    expect(await metrics()).toEqual(before);
    await expect(trigger).toBeFocused();
  });
}
test("mobile architecture selection and URL restoration", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(detail);
  await page
    .getByRole("group", { name: "Architecture" })
    .getByRole("button", { name: "ARM64", exact: true })
    .click();
  await expect(page).toHaveURL(/arch=arm64/);
  await expect(page.locator(".matrix-row:visible")).toHaveCount(1);
  await expect(
    page.locator(".matrix-row:visible a.download-link").first(),
  ).toHaveAttribute("href", /arm64-windows/);
  await page.reload();
  await expect(page.locator(".matrix-row:visible")).toHaveAttribute(
    "aria-label",
    "ARM64",
  );
});
test("home config is shareable and language switch preserves it", async ({
  page,
}) => {
  await page.goto("./");
  await page
    .getByRole("group", { name: "Architecture" })
    .getByRole("button", { name: "ARM64", exact: true })
    .click();
  if (process.env.CATALOG_FIXTURE === "1") {
    await page
      .getByRole("button", { name: "ARM64 · static · GPL", exact: true })
      .click();
  }
  await expect(page).toHaveURL(/arch=arm64/);
  await page.reload();
  await expect(page.locator("a.download-link").first()).toHaveAttribute(
    "href",
    /arm64-windows/,
  );
  await page.getByRole("link", { name: "中文", exact: true }).click();
  await expect(page).toHaveURL(/\/zh\/\?arch=arm64/);
  await expect(page.locator("a.download-link").first()).toHaveAttribute(
    "href",
    /arm64-windows/,
  );
});
test("release index only searches versions and preserves search", async ({
  page,
}) => {
  await page.goto("./releases/");
  await expect(page.getByRole("combobox")).toHaveCount(0);
  await page.getByRole("searchbox").fill(entry.upstream);
  await expect(page).toHaveURL(/q=/);
  await page.reload();
  await expect(page.getByRole("searchbox")).toHaveValue(entry.upstream);
});
test("theme selection persists and inspector is accessible in dark mode", async ({
  page,
}) => {
  await page.goto(detail);
  await page.getByLabel("Theme", { exact: true }).click();
  await page.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.locator(".info-trigger:visible").first().click();
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
test("documentation navigation and anchors", async ({ page }) => {
  await page.goto("./guide/");
  const toc = page.getByRole("navigation", { name: "On this page" });
  const link = toc.getByRole("link").first();
  const href = await link.getAttribute("href");
  await link.click();
  expect(await page.evaluate(() => location.hash)).toBe(href);
  await page
    .getByRole("navigation", { name: "Documentation" })
    .getByRole("link", { name: "Integration" })
    .click();
  await expect(page).toHaveURL(/integration\//);
});

test("home hero precedes download area and anchors correctly", async ({
  page,
}) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("./");
    const hero = page.getByRole("region", { name: "FFmpeg MSVC Prebuilt" });
    const download = page.getByRole("region", { name: "Download FFmpeg" });
    const h = await hero.boundingBox(),
      d = await download.boundingBox();
    expect(h!.y + h!.height).toBeLessThanOrEqual(d!.y + 1);
    await hero.getByRole("link", { name: "Get FFmpeg" }).click();
    await expect(page).toHaveURL(/#download$/);
    await expect(download).toBeInViewport();
  }
});
test("dark overlay has its own elevated surface", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(detail);
  await page.locator(".info-trigger:visible").first().click();
  const colors = await page.getByRole("dialog").evaluate((el) => ({
    dialog: getComputedStyle(el).backgroundColor,
    body: getComputedStyle(document.body).backgroundColor,
    code: getComputedStyle(el.querySelector("code")!).backgroundColor,
    backdrop: getComputedStyle(el, "::backdrop").backgroundColor,
    blur: getComputedStyle(el, "::backdrop").backdropFilter,
  }));
  expect(colors.dialog).toBe("rgb(41, 41, 41)");
  expect(colors.body).toBe("rgb(10, 10, 10)");
  expect(colors.code).toBe("rgb(56, 56, 56)");
  expect(colors.backdrop).not.toBe("rgba(0, 0, 0, 0)");
  expect(colors.blur).toBe("blur(3px)");
});
