import { test, expect } from "@playwright/test";
import { allEntries, searchOptions } from "../../app/domain/catalog.server";
import {
  assetUrl,
  legacyId,
  defaultVersionOptions,
} from "../../app/domain/catalog";
const entries = allEntries();
const stable = entries.find((e) => e.channel === "release")!;
const legacy = entries.find((e) => e.channel === "release" && legacyId(e));
test("static home loads and download filter is interactive", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("./");
  await expect(
    page.getByRole("heading", { name: "FFmpeg MSVC Prebuilt" }),
  ).toBeVisible();
  await page
    .getByRole("group", { name: "Architecture" })
    .getByRole("button", { name: "ARM64", exact: true })
    .click();
  if (process.env.CATALOG_FIXTURE === "1") {
    // The synthetic catalog intentionally has no ARM64 shared LGPL slot.
    // The real UI preserves the requested dimensions until the user selects an alternative.
    await page
      .getByRole("button", { name: "ARM64 · static · GPL", exact: true })
      .click();
  }
  await expect(page.locator("a.download-link").first()).toHaveAttribute(
    "href",
    /arm64-windows/,
  );
  expect(errors).toEqual([]);
});
test("deep links and client-side navigation work under the deployment base", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("./en/releases/" + stable.upstream + "/");
  await expect(
    page.getByRole("heading", {
      name: "FFmpeg " + stable.upstream,
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Snapshots", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Snapshots" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Snapshots" })).toBeVisible();
  await page.getByRole("link", { name: "中文", exact: true }).click();
  await expect(page.getByRole("heading", { name: "快照版本" })).toBeVisible();
  expect(errors).toEqual([]);
});
test("all assets have direct download hrefs in both languages' static HTML", async ({
  request,
  baseURL,
}) => {
  for (const lang of ["en", "zh"])
    for (const e of entries) {
      const response = await request.get(
        baseURL + lang + "/build/" + e.tag + "/",
      );
      expect(response.ok()).toBeTruthy();
      const html = await response.text();
      for (const v of Object.values(e.variants))
        for (const a of [v.binary, v.develop, v.debug].filter(Boolean)) {
          expect(html).toContain(
            'href="' +
              assetUrl(
                process.env.VITE_GITHUB_REPO_URL ??
                  "https://github.com/System233/ffmpeg-msvc-prebuilt",
                e.tag,
                a!,
              ) +
              '"',
          );
        }
    }
});
test("public JSON and 404 are static", async ({ request, baseURL }) => {
  const data = await request.get(baseURL + "data/index.json");
  expect(data.ok()).toBeTruthy();
  expect((await data.json()).schema).toBe(2);
  expect((await request.get(baseURL + "not-a-valid-page/")).status()).toBe(404);
});
test("unprefixed docs and localized docs are genuine pages", async ({
  page,
}) => {
  await page.goto("./guide/");
  await expect(
    page.getByRole("heading", { name: "Guide", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "中文", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "使用指南", exact: true }),
  ).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
});
test("documentation puts verification and runnable integration first, with separate reference pages", async ({
  page,
  request,
  baseURL,
}) => {
  for (const lang of ["en", "zh"]) {
    const zh = lang === "zh";
    const prefix = lang + "/";
    await page.goto("./" + prefix + "guide/");
    const article = page.locator(".prose");
    const guideText = await article.innerText();
    expect(guideText.indexOf("Get-FileHash")).toBeGreaterThan(-1);
    expect(guideText.indexOf("Get-FileHash")).toBeLessThan(
      guideText.indexOf("ffmpeg -version"),
    );
    expect(guideText.indexOf("ffmpeg -version")).toBeLessThan(
      guideText.indexOf("ffprobe -hide_banner"),
    );
    await expect(
      article.getByRole("heading", {
        name: /^(Licenses and redistribution|许可证与再分发)$/,
      }),
    ).toHaveCount(0);
    await expect(article).not.toContainText("sbom.spdx.json");
    const nav = page.locator(".doc-nav");
    await nav
      .getByRole("link", { name: zh ? "开发集成" : "Integration", exact: true })
      .click();
    await expect(page).toHaveURL(baseURL + prefix + "integration/");
    await expect(article.locator("h1")).toHaveText(
      zh ? "开发集成" : "Integration",
    );
    const integration = await article.innerText();
    expect(integration.indexOf("av_version_info()")).toBeGreaterThan(-1);
    expect(
      integration.indexOf("cmake --build build --config Release"),
    ).toBeGreaterThan(-1);
    expect(
      integration.indexOf("cmake --build build --config Release"),
    ).toBeLessThan(integration.indexOf(zh ? "工作原理" : "How it works"));
    await expect(article).toContainText("TARGET_RUNTIME_DLLS");
    for (const [path, title, required] of [
      ["packages", zh ? "构建产物" : "Build artifacts", "debug/lib/"],
      [
        "licenses",
        zh ? "许可证与再分发" : "Licenses and redistribution",
        "sbom.spdx.json",
      ],
    ]) {
      await nav.getByRole("link", { name: title, exact: true }).click();
      await expect(page).toHaveURL(baseURL + prefix + path + "/");
      await expect(article.locator("h1")).toHaveText(title);
      await expect(page).toHaveTitle(title + " | FFmpeg MSVC Prebuilt");
      await expect(nav.locator('[aria-current="page"]')).toHaveText(title);
      await expect(article).toContainText(required);
      expect(
        (await request.get(baseURL + prefix + path + "/_.data")).ok(),
      ).toBe(true);
      const hrefs = await article
        .locator("a")
        .evaluateAll((nodes) =>
          nodes.map((n) => (n as HTMLAnchorElement).href),
        );
      for (const href of hrefs) {
        const url = new URL(href);
        if (!href.startsWith(baseURL!)) continue;
        const response = await request.get(href.split("#")[0]);
        expect(response.ok()).toBe(true);
        if (url.hash)
          expect(await response.text()).toContain(
            'id="' + decodeURIComponent(url.hash.slice(1)) + '"',
          );
      }
    }
    await article
      .getByRole("link", {
        name: zh
          ? "更新历史中的许可证说明"
          : "licensing notice in the update history",
      })
      .click();
    await expect(
      page.locator(zh ? '[id="历史-lgpl-构建"]' : '[id="legacy-lgpl-builds"]'),
    ).toBeInViewport();
  }
  for (const path of ["packages", "licenses"]) {
    expect((await request.get(baseURL + path + "/")).ok()).toBe(true);
  }
});

test("download options have concise adaptive hover and keyboard tooltips", async ({
  page,
}) => {
  for (const lang of ["zh", "en"]) {
    const zh = lang === "zh";
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("./" + lang + "/");
    const architecture = page.getByRole("group", {
      name: zh ? "架构" : "Architecture",
      exact: true,
    });
    const x64 = architecture.getByRole("button", { name: "X64", exact: true });
    const linkage = page.getByRole("group", {
      name: zh ? "链接方式" : "Linkage",
    });
    const shared = linkage.getByRole("button", {
      name: zh ? "共享库" : "Shared",
      exact: true,
    });
    const tip = page.getByRole("tooltip");
    const before = page.url();
    await x64.hover();
    await expect(tip).toHaveText(
      zh
        ? "适用于 Intel 和 AMD 的 64 位 Windows 应用。"
        : "For 64-bit Intel and AMD Windows applications.",
    );
    const bounds = await tip.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
    await shared.hover();
    await expect(tip).toContainText(zh ? "动态链接" : "dynamic linking");
    await page.mouse.move(0, 0);
    await expect(tip).toHaveCount(0);
    await shared.focus();
    await expect(tip).toContainText(zh ? "动态链接" : "dynamic linking");
    await page.keyboard.press("Escape");
    await expect(tip).toHaveCount(0);
    expect(page.url()).toBe(before);
    const picker = page.locator(".version-trigger");
    await picker.hover();
    await expect(tip).toContainText(zh ? "选择需要下载" : "Select the FFmpeg");
    await picker.click();
    await expect(page.locator(".version-popup")).toBeVisible();
    await expect(tip).toHaveCount(0);
    await page.locator('[data-filter="lts"]').hover();
    await expect(tip).toContainText(zh ? "长期支持" : "long-term support");
    await page.mouse.move(0, 0);
    await expect(tip).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(page.locator(".version-popup")).toHaveCount(0);
  }
});

test("Chinese linkage labels and static SDK distribution rationale", async ({
  page,
}) => {
  await page.goto("./zh/");
  const linkage = page.getByRole("group", { name: "链接方式" });
  await expect(
    linkage.getByRole("button", { name: "共享库", exact: true }),
  ).toBeVisible();
  await expect(
    linkage.getByRole("button", { name: "静态库", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".quick-info")).toContainText("共享库");
  await page.goto("./zh/releases/" + stable.upstream + "/");
  await expect(
    page.locator(".matrix-group-title").filter({ hasText: "共享库" }).first(),
  ).toBeVisible();
  await expect(
    page.locator(".matrix-group-title").filter({ hasText: "静态库" }).first(),
  ).toBeVisible();
  await page.goto("./zh/packages/");
  await expect(page.locator(".prose")).toContainText("体积过大");
  await page.goto("./en/packages/");
  await expect(page.locator(".prose")).toContainText("too large to distribute");
  await page.goto("./zh/history/");
  await expect(page.locator(".prose")).not.toContainText(
    /不代表|不单独证明|不追溯改变/,
  );
  await expect(page.locator('[id="历史-lgpl-构建"]')).toBeVisible();
});

test("mobile navigation, release filters and legacy URLs", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("./en/");
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await page.getByRole("link", { name: "All versions", exact: true }).click();
  await page.getByRole("searchbox").fill(stable.upstream);
  await expect(
    page.getByRole("link", { name: new RegExp("FFmpeg " + stable.upstream) }),
  ).toBeVisible();
  if (legacy) await page.goto("./en/releases/" + legacyId(legacy) + ".html");
  else await page.goto("./en/releases/" + stable.upstream + "/");
  await expect(
    page.getByRole("heading", {
      name: "FFmpeg " + (legacy?.upstream ?? stable.upstream),
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
test("download information is usable with JavaScript disabled", async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto(baseURL + "en/build/" + stable.tag + "/");
  await expect(page.locator("a.download-link").first()).toBeVisible();
  await context.close();
});

test("searchable version picker filters LTS and snapshots without changing selection", async ({
  page,
}) => {
  await page.goto("./en/");
  const trigger = page.locator(".version-trigger");
  const original = await trigger.locator(".version-trigger-label").innerText();
  await trigger.click();
  const popup = page.locator(".version-popup");
  const search = popup.getByRole("combobox");
  await expect(search).toBeVisible();
  await page.locator('.version-filter-tag[data-filter="lts"]').click();
  const rows = popup.getByRole("option");
  await expect.poll(() => rows.count()).toBeGreaterThan(0);
  expect(
    await rows.evaluateAll((nodes) =>
      nodes.every(
        (n) =>
          n.textContent?.includes("LTS") &&
          !n.getAttribute("data-tag")?.includes("master"),
      ),
    ),
  ).toBe(true);
  await expect(trigger.locator(".version-trigger-label")).toHaveText(original);
  await page.locator('.version-filter-tag[data-filter="snapshot"]').click();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Snapshot");
  await expect(trigger.locator(".version-trigger-label")).toHaveText(original);
  await page.locator('.version-filter-tag[data-filter="all"]').click();
  await search.fill("not-a-version");
  await expect(popup.getByText("No matching versions.")).toBeVisible();
  await search.fill("8.1.3");
  await expect(rows).toHaveCount(1);
  await search.press("ArrowDown");
  await search.press("Enter");
  await expect(trigger).toContainText("8.1.3");
  await expect(page).toHaveURL(/version=ffmpeg-8\.1\.3/);
  await trigger.click();
  await page.locator('.version-filter-tag[data-filter="snapshot"]').click();
  await rows.first().click();
  await expect(trigger).toContainText("Snapshot");
  await expect(page).toHaveURL(/version=ffmpeg-/);
  await trigger.click();
  await search.press("Escape");
  await expect(popup).not.toBeVisible();
  await expect(trigger).toBeFocused();
});

test("Chinese navigation, FAQ and package copy", async ({ page }) => {
  await page.goto("./zh/");
  await expect(
    page.getByRole("link", { name: "全部版本", exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "快照版本", exact: true }).first(),
  ).toBeVisible();
  await expect(page.locator(".package-downloads .primary")).toContainText(
    "二进制",
  );
  await expect(page.locator(".package-note")).not.toContainText("•");
  const faq = page.locator(".home-faq");
  await expect(faq.locator("details")).toHaveCount(7);
  await faq.getByText("如何安装和使用 FFmpeg？", { exact: true }).click();
  await expect(faq.locator("details[open]")).toContainText("ffmpeg -version");
  await page.goto("./zh/releases/");
  await page.locator('.version-filter-tag[data-filter="lts"]').click();
  await expect(page).toHaveURL(/lts=1/);
  expect(
    await page
      .locator(".release-row")
      .evaluateAll(
        (nodes) =>
          nodes.length > 0 &&
          nodes.every((n) => n.querySelector(".version-badge")),
      ),
  ).toBe(true);
});

test("inline filter tags and stable search geometry", async ({ page }) => {
  for (const lang of ["en", "zh"]) {
    for (const [width, height] of [
      [1440, 900],
      [800, 600],
      [390, 844],
      [320, 568],
    ]) {
      await page.setViewportSize({ width, height });
      await page.goto("./" + lang + "/");
      const trigger = page.locator(".version-trigger");
      await trigger.scrollIntoViewIfNeeded();
      await trigger.click();
      const popup = page.locator(".version-popup");
      const search = popup.getByRole("combobox");
      const filters = popup.locator(".version-filter-tag");
      await expect(search).toBeVisible();
      await expect(filters).toHaveCount(3);
      await expect
        .poll(async () => Math.round((await popup.boundingBox())!.height))
        .toBeGreaterThan(85);
      const rect = async () =>
        await search.evaluate((n) => {
          const r = n.getBoundingClientRect(),
            p = n.closest(".version-popup")!.getBoundingClientRect();
          return [r.x, r.y, r.width, r.height, p.x, p.y, p.width, p.height].map(
            (x) => Math.round(x),
          );
        });
      const original = await rect();
      expect(
        await filters
          .first()
          .evaluate(
            (n) =>
              n.closest(".version-search")?.querySelector("input") !== null,
          ),
      ).toBe(true);
      const f = await filters.first().boundingBox(),
        inputBox = await search.boundingBox();
      expect(f!.x).toBeGreaterThanOrEqual(inputBox!.x + inputBox!.width - 1);
      expect(
        Math.abs(f!.y + f!.height / 2 - (inputBox!.y + inputBox!.height / 2)),
      ).toBeLessThan(2);

      const check = async () => {
        await expect.poll(rect).toEqual(original);
      };
      expect(
        await filters.evaluateAll((ns) =>
          ns.every((n) => {
            const r = n.getBoundingClientRect();
            return r.height <= 28 && r.width <= 90;
          }),
        ),
      ).toBe(true);
      await page.locator('.version-filter-tag[data-filter="lts"]').click();
      await check();
      await page.locator('.version-filter-tag[data-filter="snapshot"]').click();
      await expect(popup.getByRole("option")).toHaveCount(1);
      await check();
      await page.locator('.version-filter-tag[data-filter="all"]').click();
      await check();
      await search.fill("no-matching-version");
      await expect(popup.getByRole("option")).toHaveCount(0);
      await check();
      await search.fill("8.1.3");
      await expect(popup.getByRole("option")).toHaveCount(1);
      await check();
      await search.fill("");
      await check();
      expect(
        await popup.evaluate((n) => {
          const r = n.getBoundingClientRect();
          return (
            r.top >= -1 &&
            r.bottom <= innerHeight + 1 &&
            r.left >= -1 &&
            r.right <= innerWidth + 1
          );
        }),
      ).toBe(true);
      await search.press("Escape");
      await page.goto("./" + lang + "/releases/");
      const input = page.getByRole("searchbox");
      const before = await input.boundingBox();
      const controls = page.locator(".release-search .version-filter-tag");
      await expect(controls).toHaveCount(2);
      expect(
        await controls.evaluateAll((ns) =>
          ns.every((n) => {
            const r = n.getBoundingClientRect();
            return r.height <= 28 && r.width <= 90;
          }),
        ),
      ).toBe(true);
      await page.locator('.version-filter-tag[data-filter="lts"]').click();
      await expect(page).toHaveURL(/lts=1/);
      expect(await input.boundingBox()).toEqual(before);
      await input.fill("no-matching-version");
      await expect(page.locator(".release-row")).toHaveCount(0);
      expect(await input.boundingBox()).toEqual(before);
    }
  }
});

test("inline filter tags support keyboard selection without closing the combobox", async ({
  page,
}) => {
  await page.goto("./en/");
  await page.locator(".version-trigger").click();
  const popup = page.locator(".version-popup");
  const tags = popup.locator(".version-filter-tag");
  await expect(tags).toHaveCount(3);
  await expect(tags.nth(0)).toHaveAttribute("aria-pressed", "true");
  await tags.nth(1).focus();
  await tags.nth(1).press("Enter");
  await expect(tags.nth(1)).toHaveAttribute("aria-pressed", "true");
  await expect(tags.nth(0)).toHaveAttribute("aria-pressed", "false");
  await expect(popup).toBeVisible();
  await tags.nth(2).focus();
  await tags.nth(2).press("Space");
  await expect(tags.nth(2)).toHaveAttribute("aria-pressed", "true");
  await expect(popup.getByRole("option")).toHaveCount(1);
  await expect(popup).toBeVisible();
  await popup.getByRole("combobox").press("Escape");
  await expect(popup).not.toBeVisible();
  await page.goto("./en/releases/");
  const lts = page.locator(
    '.release-search .version-filter-tag[data-filter="lts"]',
  );
  await lts.focus();
  await lts.press("Enter");
  await expect(page).toHaveURL(/lts=1/);
  await expect(lts).toHaveAttribute("aria-pressed", "true");
});

test("version popup adapts to page scrolling without resetting the filter", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 600 });
  await page.goto("./en/");
  const trigger = page.locator(".version-trigger");
  await page.evaluate(() => window.scrollTo(0, 0));
  const original = (await trigger.boundingBox())!;
  await page.setViewportSize({
    width: 1024,
    height: Math.max(480, Math.round(original.y + original.height + 95)),
  });
  await trigger.click();
  const positioner = page.locator(".version-positioner");
  const popup = page.locator(".version-popup");
  const search = popup.getByRole("combobox");
  await expect(positioner).toHaveAttribute("data-side", "top");
  await popup.locator('.version-filter-tag[data-filter="lts"]').click();
  const scrollToAnchor = async (y: number) =>
    await trigger.evaluate(
      (n, y) => window.scrollBy(0, n.getBoundingClientRect().top - y),
      y,
    );
  await scrollToAnchor(75);
  await expect(positioner).toHaveAttribute("data-side", "bottom");
  await expect(
    popup.locator('.version-filter-tag[data-filter="lts"]'),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(search).toBeVisible();
  await expect
    .poll(async () => {
      const t = (await trigger.boundingBox())!,
        p = (await popup.boundingBox())!;
      return Math.abs(p.y - t.y - t.height - 6);
    })
    .toBeLessThan(2);
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(positioner).toHaveAttribute("data-side", "top");
  await expect
    .poll(async () => {
      const t = (await trigger.boundingBox())!,
        p = (await popup.boundingBox())!;
      return Math.abs(t.y - p.y - p.height - 6);
    })
    .toBeLessThan(2);
  await expect(search).toBeVisible();
});

test("FAQ provides actionable answers and valid localized documentation anchors", async ({
  page,
}) => {
  for (const lang of ["en", "zh"]) {
    await page.setViewportSize({ width: 320, height: 700 });
    await page.goto("./" + lang + "/");
    const faq = page.locator(".home-faq");
    const items = faq.locator("details.faq-item");
    await expect(items).toHaveCount(7);
    await expect(items.locator(".faq-answer")).toHaveCount(7);
    await expect(
      items
        .locator("a")
        .filter({ hasText: /^(Read the documentation|查看文档)$/ }),
    ).toHaveCount(0);
    await expect(faq.locator(".faq-footer a")).toHaveCount(1);
    await expect(faq.locator(".faq-footer")).not.toContainText(
      /Need more details|需要更详细的说明/,
    );
    await expect(faq.locator(".faq-footer a")).toHaveText(
      lang === "zh" ? "查看文档" : "Read the documentation",
    );
    for (const item of await items.all()) await item.locator("summary").click();
    expect(
      await items.evaluateAll((nodes) =>
        nodes.every(
          (n) =>
            (n.querySelector(".faq-answer")?.textContent?.trim().length ?? 0) >=
            80,
        ),
      ),
    ).toBe(true);
    await expect(faq.locator("pre")).toHaveCount(3);
    const linkageAnswer = items.nth(1).locator(".faq-answer");
    await expect(linkageAnswer).toContainText(
      lang === "zh" ? "一般选择共享库" : "Shared is the usual choice",
    );
    await expect(linkageAnswer.locator("li").first()).toContainText(
      lang === "zh" ? "共享库（推荐）" : "Shared (recommended)",
    );
    expect(
      await items.locator("a").evaluateAll((nodes) =>
        nodes.every((n) => {
          const range = document.createRange();
          range.setStart(n.parentNode!, 0);
          range.setEndBefore(n);
          return /\s$/.test(range.toString());
        }),
      ),
    ).toBe(true);
    for (const block of await faq.locator("pre code.hljs").all()) {
      expect(
        await block.locator("span[class^='hljs-']").count(),
      ).toBeGreaterThan(0);
    }
    await expect(faq.locator("pre code.hljs")).toHaveCount(3);
    const token = faq.locator("pre code.hljs span[class^='hljs-']").first();
    const light = await token.evaluate((n) => {
      document.documentElement.dataset.theme = "light";
      return getComputedStyle(n).color;
    });
    const dark = await token.evaluate((n) => {
      document.documentElement.dataset.theme = "dark";
      return getComputedStyle(n).color;
    });
    expect(light).not.toBe(dark);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const links = await items
      .locator("a")
      .evaluateAll((nodes) => nodes.map((n) => (n as HTMLAnchorElement).href));
    expect(links.length).toBeGreaterThanOrEqual(10);
    for (const href of new Set(links)) {
      const url = new URL(href);
      expect(url.pathname).toContain("/" + lang + "/");
      expect(url.hash).not.toBe("");
      const response = await page.request.get(href.split("#")[0]);
      expect(response.ok()).toBe(true);
      expect(await response.text()).toContain(
        'id="' + decodeURIComponent(url.hash.slice(1)) + '"',
      );
    }
    for (const link of await faq
      .locator(".faq-footer a")
      .evaluateAll((nodes) =>
        nodes.map((n) => (n as HTMLAnchorElement).href),
      )) {
      expect((await page.request.get(link)).ok()).toBe(true);
    }
    const firstLink = items.first().locator("a").first();
    const href = await firstLink.getAttribute("href");
    await firstLink.click();
    await expect(page).toHaveURL(
      (url) =>
        url.pathname.endsWith("/" + lang + "/guide/") &&
        decodeURIComponent(url.hash) ===
          decodeURIComponent(href!.slice(href!.indexOf("#"))),
    );
    const id = decodeURIComponent(href!.slice(href!.indexOf("#") + 1));
    await expect(page.locator('[id="' + id + '"]')).toBeInViewport();
  }
});

test("FAQ is useful without JavaScript", async ({ browser, baseURL }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    baseURL,
  });
  try {
    const page = await context.newPage();
    await page.goto("./zh/");
    const item = page
      .locator(".faq-item")
      .filter({ hasText: "如何安装和使用 FFmpeg？" });
    await item.locator("summary").click();
    await expect(item.locator("pre")).toContainText("ffmpeg -version");
    expect(await item.locator("pre code.hljs span").count()).toBeGreaterThan(0);
    await item.getByRole("link", { name: "安装与基本命令" }).click();
    await expect(page.locator('[id="安装与基本命令"]')).toBeInViewport();
    expect(
      await page.locator(".prose pre code.hljs span").count(),
    ).toBeGreaterThan(0);
  } finally {
    await context.close();
  }
});

test("self-build documentation is available in both languages with styled links", async ({
  page,
}) => {
  for (const lang of ["en", "zh"]) {
    await page.goto("./" + lang + "/guide/");
    const nav = page.locator(".doc-nav");
    const build = nav.getByRole("link", {
      name: lang === "zh" ? "自行构建" : "Build from source",
      exact: true,
    });
    await expect(build).toBeVisible();
    await build.click();
    await expect(page).toHaveURL(new RegExp("/" + lang + "/self-build/"));
    await expect(page.locator("main h1")).toHaveText(
      lang === "zh" ? "自行构建" : "Build from source",
    );
    await expect(page.locator(".prose")).toContainText(
      "python -m ffbuild generate 8.1.3",
    );
    await expect(page.locator(".prose")).toContainText("ffmpeg[all-gpl]");
    await expect(page.locator(".prose pre code.hljs").first()).toBeVisible();
    await expect(page.locator(".doc-nav a.active")).toHaveText(
      lang === "zh" ? "自行构建" : "Build from source",
    );
    const link = page.locator(".prose a").first();
    const color = await link.evaluate((n) => {
      document.documentElement.dataset.theme = "light";
      return getComputedStyle(n).color;
    });
    const dark = await link.evaluate((n) => {
      document.documentElement.dataset.theme = "dark";
      return getComputedStyle(n).color;
    });
    expect(color).toBe("rgb(29, 78, 216)");
    expect(dark).toBe("rgb(147, 197, 253)");
    await page.goto("./" + lang + "/");
    const faq = page.locator(".faq-item");
    await expect(faq.locator(".faq-answer > p:first-child")).toHaveCount(7);
    await faq.first().locator("summary").click();
    expect(
      await faq
        .first()
        .locator("a")
        .first()
        .evaluate((n) => getComputedStyle(n).color),
    ).not.toBe(
      await faq
        .first()
        .locator(".faq-answer")
        .evaluate((n) => getComputedStyle(n).color),
    );
  }
});

test("detail back buttons follow browser history, not parent routes", async ({
  page,
}) => {
  await page.goto("./en/?arch=arm64#download");
  const home = page.url();
  await page.getByRole("link", { name: "View all variants" }).click();
  await expect(page).toHaveURL(/\/build\//);
  const build = page.url();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(page).toHaveURL(home);
  await page.goForward();
  await expect(page).toHaveURL(build);
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(page).toHaveURL(home);
  await page.locator(".hero-release a").click();
  await expect(page).toHaveURL(/\/releases\/[^/]+\//);
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(page).toHaveURL(home);
  await page.goto("./zh/guide/#快速开始");
  const docs = page.url();
  const snapshot = entries.find((e) => e.channel === "master")!;
  await page.goto("./zh/master/" + snapshot.date.slice(0, 4) + "/");
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await expect(page).toHaveURL(docs);
  await page.goto("./zh/build/" + snapshot.tag + "/");
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await expect(page).toHaveURL(docs);
  await page.goto("./en/releases/?q=" + stable.upstream + "&lts=0");
  const filtered = page.url();
  await page.locator(".release-row").first().click();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(page).toHaveURL(filtered);
});

test("back control changes label and uses the parent for external or absent history", async ({
  page,
  baseURL,
}) => {
  const detail = new URL("en/build/" + stable.tag + "/", baseURL).href;
  const parent = new URL("en/releases/" + stable.upstream + "/", baseURL).href;
  const list = new URL("en/releases/", baseURL).href;
  const back = page.locator(".history-back");
  await page.goto(detail);
  await expect(back).toHaveText("Back to FFmpeg " + stable.upstream);
  await expect(back).toHaveAttribute("href", new URL(parent).pathname);
  await page.reload();
  await expect(back).toHaveText("Back to FFmpeg " + stable.upstream);
  await back.click();
  await expect(page).toHaveURL(parent);
  await expect(back).toHaveText("Back to all versions");
  await back.click();
  await expect(page).toHaveURL(list);
  for (const url of [
    new URL("/unrelated-site-page", baseURL).href,
    "https://outside.test/previous",
  ]) {
    await page.route(url, (route) =>
      route.fulfill({
        contentType: "text/html",
        body: '<a href="' + detail + '">Open download</a>',
      }),
    );
    await page.goto(url);
    await page.getByRole("link", { name: "Open download" }).click();
    await expect(page).toHaveURL(detail);
    await expect(back).toHaveText("Back to FFmpeg " + stable.upstream);
    await page.reload();
    await expect(back).toHaveText("Back to FFmpeg " + stable.upstream);
    await back.click();
    await expect(page).toHaveURL(parent);
    await expect(back).toHaveText("Back to all versions");
    await back.click();
    await expect(page).toHaveURL(list);
    await page.getByRole("link", { name: "Download", exact: true }).click();
    await expect(page).toHaveURL(/\/en\/$/);
    const home = page.url();
    await page.getByRole("link", { name: "View all variants" }).click();
    await expect(
      page.getByRole("button", { name: "Back", exact: true }),
    ).toBeVisible();
    await page.reload();
    await expect(
      page.getByRole("button", { name: "Back", exact: true }),
    ).toBeVisible();
    await back.click();
    await expect(page).toHaveURL(home);
    await page.goForward();
    await expect(back).toHaveText("Back");
  }
});

test("older browsers use parent links when in-app history cannot be proven", async ({
  page,
  baseURL,
}) => {
  await page.addInitScript(() =>
    Object.defineProperty(window, "navigation", {
      value: undefined,
      configurable: true,
    }),
  );
  await page.goto("./en/build/" + stable.tag + "/");
  const back = page.locator(".history-back");
  await expect(back).toHaveText("Back to FFmpeg " + stable.upstream);
  await page.getByRole("link", { name: "Download", exact: true }).click();
  await expect(page).toHaveURL(/\/en\/$/);
  const home = page.url();
  await page.getByRole("link", { name: "View all variants" }).click();
  await expect(back).toHaveText("Back");
  await back.click();
  await expect(page).toHaveURL(home);
  await page.goForward();
  await expect(back).toHaveText("Back");
  const href = page.url();
  const selected = entries.find((e) => href.endsWith("/build/" + e.tag + "/"))!;
  await page.reload();
  await expect(back).toHaveText("Back to FFmpeg " + selected.upstream);
  await back.click();
  await expect(page).toHaveURL(
    baseURL + "en/releases/" + selected.upstream + "/",
  );
});

test("localized parent labels and links work without JavaScript", async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    baseURL,
  });
  try {
    const page = await context.newPage();
    await page.goto("./zh/build/" + stable.tag + "/");
    await page
      .getByRole("link", {
        name: "返回 FFmpeg " + stable.upstream,
        exact: true,
      })
      .click();
    await expect(page).toHaveURL(
      baseURL + "zh/releases/" + stable.upstream + "/",
    );
    await page.getByRole("link", { name: "返回全部版本", exact: true }).click();
    await expect(page).toHaveURL(baseURL + "zh/releases/");
    const snapshot = entries.find((e) => e.channel === "master")!;
    const year = snapshot.date.slice(0, 4);
    await page.goto("./zh/build/" + snapshot.tag + "/");
    await page
      .getByRole("link", { name: "返回 " + year + " 年快照", exact: true })
      .click();
    await expect(page).toHaveURL(baseURL + "zh/master/" + year + "/");
    await page.getByRole("link", { name: "返回快照版本", exact: true }).click();
    await expect(page).toHaveURL(baseURL + "zh/master/");
  } finally {
    await context.close();
  }
});

test("historical LGPL notice is scoped to the selected variant and links to localized details", async ({
  page,
  request,
  baseURL,
}) => {
  const old = entries.find(
    (entry) =>
      entry.channel === "release" &&
      Object.values(entry.variants).some(
        (v) => v.note === "legacy-lgpl-licensing",
      ),
  )!;
  expect(old).toBeDefined();
  const slot = Object.keys(old.variants).find((k) => old.variants[k].note)!;
  const [arch, , linkage] = slot.split("-");
  const gplSlot = Object.keys(old.variants).find((k) => k.endsWith("-gpl"))!;
  const [gplArch, , gplLinkage] = gplSlot.split("-");
  for (const lang of ["en", "zh"]) {
    const label = lang === "zh" ? "查看详情" : "View details";
    const docTitle = lang === "zh" ? "更新历史" : "Update history";
    const anchor = lang === "zh" ? "历史-lgpl-构建" : "legacy-lgpl-builds";
    const target = lang + "/history/";
    const response = await request.get(
      baseURL + lang + "/build/" + old.tag + "/",
    );
    expect(response.ok()).toBe(true);
    expect(await response.text()).toContain("variant-notice");
    await page.goto("./" + lang + "/build/" + old.tag + "/");
    const notice = page.locator(".build-section > .variant-notice");
    await expect(notice).toBeVisible();
    await expect(notice.locator(".notice-icon")).toBeVisible();
    await expect(notice).toHaveText(
      lang === "zh"
        ? "此构建的 LGPL 版本包含 GPL 许可组件，不能视为已确认合规的 LGPL 构建。 查看详情 ↗"
        : "The LGPL variant of this build contains GPL-licensed components and should not be treated as a verified LGPL build. View details ↗",
    );
    await page.setViewportSize({ width: 320, height: 720 });
    for (const [theme, color] of [
      ["light", "rgb(146, 64, 14)"],
      ["dark", "rgb(251, 191, 36)"],
    ]) {
      await notice.evaluate(
        (n, theme) => (document.documentElement.dataset.theme = theme),
        theme,
      );
      await expect(notice).toHaveCSS("color", color);
      await expect(notice.locator(".notice-icon")).toHaveCSS("color", color);
      await expect(notice.locator("a")).toHaveCSS("color", color);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    await notice.getByRole("link", { name: new RegExp(label) }).click();
    await expect(page).toHaveURL(new RegExp("/" + target));
    await expect(
      page.getByRole("heading", { name: docTitle, exact: true }),
    ).toBeVisible();
    expect(
      await page
        .locator("h2, h3")
        .evaluateAll((nodes) => nodes.map((n) => n.id)),
    ).toContain(anchor);
    expect(decodeURIComponent(new URL(page.url()).hash)).toBe("#" + anchor);
    await expect(page.locator('[id="' + anchor + '"]')).toBeInViewport();
    await expect(page).toHaveTitle(docTitle + " | FFmpeg MSVC Prebuilt");
    await expect(page.locator('.doc-nav [aria-current="page"]')).toHaveText(
      docTitle,
    );
    await expect(page.locator(".prose h2")).toHaveText([
      "2026-11-27",
      "2026-11-26",
      "2026-11-25",
      "2026-11-22",
      "2026-11-20",
      "2026-11-06",
      "2026-11-05",
      "2026-10-23",
      "2026-09-21",
      "2026-09-19",
      "2026-08-12",
      "2026-06-23",
      "2026-06-22",
      "2026-06-21",
    ]);
    const history = page.locator(".prose");
    await expect(history).not.toContainText(
      /demo|fixture|演示站点|下载站点重构|下载站点与元数据|V2 JSON|download site|release catalog/i,
    );
    await expect(history).toContainText("MPGLIB");
    await expect(history).toContainText("Lensfun");
    await expect(history).toContainText("OpenSSL");
    await expect(history).toContainText("fft.c");
    await expect(page.locator(".prose a[href*='/issues/']")).toHaveCount(0);
    await page.goto(
      "./" +
        lang +
        "/?version=" +
        old.tag +
        "&arch=" +
        arch +
        "&linkage=" +
        linkage +
        "&license=lgpl",
    );
    await expect(
      page.locator(".package-downloads + .variant-notice"),
    ).toBeVisible();
    await page.goto(
      "./" +
        lang +
        "/?version=" +
        old.tag +
        "&arch=" +
        gplArch +
        "&linkage=" +
        gplLinkage +
        "&license=gpl",
    );
    await expect(
      page.locator(".package-downloads + .variant-notice"),
    ).toHaveCount(0);
  }
  const native = entries.find((e) =>
    Object.values(e.variants).some((v) => v.abi),
  );
  if (native) {
    await page.goto("./en/build/" + native.tag + "/");
    await expect(page.locator(".build-section > .variant-notice")).toHaveCount(
      0,
    );
  }
});

test("warning icons display one local explanation without changing selection", async ({
  page,
}) => {
  const old = entries.find(
    (e) =>
      e.channel === "release" && Object.values(e.variants).some((v) => v.note),
  )!;
  const other = entries.find(
    (e) =>
      e.tag !== old.tag &&
      e.channel === "release" &&
      Object.values(e.variants).some((v) => v.note),
  )!;
  const pop = page.locator(".version-warning-popover");
  for (const lang of ["en", "zh"]) {
    for (const width of [320, 390, 1280]) {
      await page.setViewportSize({ width, height: 844 });
      await page.goto(
        "./" +
          lang +
          "/?version=" +
          old.tag +
          "&arch=x64&linkage=shared&license=lgpl",
      );
      const url = page.url();
      await expect(pop).toHaveCount(1);
      await expect(pop).not.toBeVisible();
      const assertNotice = async (before: string) => {
        await expect(pop).toBeVisible();
        await expect(pop.locator(".notice-icon")).toBeVisible();
        await expect(pop.locator("p")).toHaveText(
          lang === "zh"
            ? "此构建的 LGPL 版本包含 GPL 许可组件，不能视为已确认合规的 LGPL 构建。 查看详情 ↗"
            : "The LGPL variant of this build contains GPL-licensed components and should not be treated as a verified LGPL build. View details ↗",
        );
        await expect(
          pop.getByRole("link", {
            name: lang === "zh" ? /查看详情/ : /View details/,
          }),
        ).toBeVisible();
        await expect(pop.getByRole("button")).toHaveCount(0);
        await expect(page).toHaveURL(before);
        expect(
          await pop.evaluate((n) => {
            const r = n.getBoundingClientRect();
            return (
              r.left >= 0 &&
              r.top >= 0 &&
              r.right <= innerWidth + 1 &&
              r.bottom <= innerHeight + 1
            );
          }),
        ).toBe(true);
      };
      const trigger = page.locator(".version-trigger-wrap > .version-warning");
      await trigger.click();
      await assertNotice(url);
      await page.keyboard.press("Escape");
      await expect(pop).not.toBeVisible();
      await page.locator(".version-trigger").click();
      const popup = page.locator(".version-popup"),
        search = popup.getByRole("combobox");
      await search.fill(other.tag);
      await popup.locator(".version-option .version-warning").click();
      await assertNotice(url);
      await expect(popup).toBeVisible();
      await expect(search).toHaveValue(other.tag);
      await expect(popup.locator(".version-warning-help")).toHaveCount(0);
      await page.keyboard.press("Escape");
      await expect(pop).not.toBeVisible();
      await expect(popup).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(popup).not.toBeVisible();
      await trigger.focus();
      await trigger.press("Enter");
      await assertNotice(url);
      await page.keyboard.press("Escape");
      await expect(pop).not.toBeVisible();
      await page.goto(
        "./" + lang + "/releases/?q=" + encodeURIComponent(old.tag),
      );
      const listUrl = page.url();
      await page.locator(".release-row .version-warning").click();
      await assertNotice(listUrl);
      await page.keyboard.press("Escape");
      await page.goto("./" + lang + "/releases/" + old.upstream + "/");
      const majorUrl = page.url();
      await expect(page.locator(".meta-line .version-warning")).toHaveCount(0);
      await expect(
        page.locator(".build-section > .variant-notice .notice-icon"),
      ).toBeVisible();
      await expect(page.locator(".page-head .version-warning")).toHaveCount(0);
      const warningHistory = page.locator("#history .version-warning");
      if (await warningHistory.count()) {
        await warningHistory.first().click();
        await assertNotice(majorUrl);
      }
    }
  }
});
test("major catalog exposes only current representatives by default and finds folded versions", async ({
  page,
}) => {
  const stable = entries.filter((e) => e.channel === "release");
  const majors = new Set(stable.map((e) => e.upstream.split(".")[0]));
  const visible = defaultVersionOptions(searchOptions());
  await page.goto("./en/");
  await page.locator(".version-trigger").click();
  const popup = page.locator(".version-popup");
  await expect(popup.getByRole("option")).toHaveCount(visible.length);
  expect(
    await popup
      .getByRole("option")
      .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("data-tag"))),
  ).toEqual(visible.map((o) => o.tag));
  await page.goto("./en/releases/");
  await expect(page.locator(".release-row")).toHaveCount(majors.size);
  await expect(page.locator(".release-row .version-warning")).toHaveCount(0);
  const old =
    stable.find((e) => e.upstream === "9.0.1") ??
    stable.find((e) => e.upstream === "8.1.3")!;
  await page.getByRole("searchbox").fill(old.tag);
  await expect(page.locator(".release-row")).toHaveCount(1);
  await page.locator(".release-row-target").click();
  await expect(page).toHaveURL(new RegExp("/build/" + old.tag + "/"));
});

test("warning details work without JavaScript", async ({
  browser,
  baseURL,
}) => {
  const ctx = await browser.newContext({ javaScriptEnabled: false, baseURL });
  try {
    const page = await ctx.newPage();
    await page.goto("./zh/releases/9.1/");
    const url = page.url();
    await page.locator(".release-row .version-warning").first().click();
    const pop = page.locator(".version-warning-popover");
    await expect(pop).toBeVisible();
    await expect(pop).toContainText("此构建的 LGPL 版本包含 GPL 许可组件");
    await expect(page).toHaveURL(url);
    await expect(pop.getByRole("button")).toHaveCount(0);
    await page
      .getByRole("heading", { name: "FFmpeg 9.1", exact: true })
      .click();
    await expect(pop).not.toBeVisible();
  } finally {
    await ctx.close();
  }
});

test("other versions jump does not consume the page back action", async ({
  page,
}) => {
  const major = stable.upstream.split(".")[0] + ".x";
  for (const lang of ["en", "zh"]) {
    const original = "./" + lang + "/releases/?q=" + major;
    await page.goto(original);
    const list = page.url();
    await page.locator(".release-row-target").first().click();
    await expect(page).toHaveURL(
      new RegExp("/releases/" + stable.upstream.replace(/\./g, "\\.") + "/$"),
    );
    const detail = page.url();
    const jump = page.getByRole("link", {
      name: lang === "zh" ? /其他版本/ : /Other versions/,
    });
    await expect(jump).toBeVisible();
    await jump.click();
    await expect(page.locator("#history")).toBeInViewport();
    await expect(page).toHaveURL(detail);
    await page.locator(".history-back").click();
    await expect(page).toHaveURL(list);
  }
});
test("warning hover dismisses on exit but permits reading and following its link", async ({
  page,
}) => {
  await page.goto("./zh/releases/9.1/");
  const icon = page.locator(".release-row .version-warning").first();
  const popup = page.locator(".version-warning-popover");
  await icon.hover();
  await expect(popup).toBeVisible();
  await popup.hover();
  await expect(popup).toBeVisible();
  await page.waitForTimeout(220);
  await expect(popup).toBeVisible();
  await page.getByRole("heading", { name: "其他版本", exact: true }).hover();
  await expect(popup).not.toBeVisible();
  await icon.hover();
  await expect(popup).toBeVisible();
  await icon.click();
  await expect(popup).toBeVisible();
  await page.getByRole("heading", { name: "其他版本", exact: true }).hover();
  await expect(popup).not.toBeVisible();
});

test("configured LTS families are labeled and filterable on real catalog", async ({
  page,
}) => {
  const expected = ["9.1", "7.1", "5.1", "4.4"];
  const actual = entries
    .filter((e) => e.channel === "release" && e.lts)
    .map((e) => e.upstream.split(".").slice(0, 2).join("."));
  expect([...new Set(actual)].sort()).toEqual([...expected].sort());
  for (const e of entries) {
    expect(e.lts).toBe(
      e.channel === "release" &&
        expected.includes(e.upstream.split(".").slice(0, 2).join(".")),
    );
  }
  await page.goto("./zh/");
  await expect(
    page.locator(".version-trigger-wrap > .version-badge"),
  ).toHaveText("LTS");
  await page.locator(".version-trigger").click();
  const popup = page.locator(".version-popup");
  await popup.locator('[data-filter="lts"]').click();
  await expect(popup.getByRole("option")).toHaveCount(4);
  for (const family of expected) {
    const option = popup.locator(".version-option").filter({
      has: page.locator(".version-option-title").filter({
        hasText: new RegExp(
          "^FFmpeg " + family.replace(".", "\\.") + "(?:\\.\\d+)?$",
        ),
      }),
    });
    await expect(option).toHaveCount(1);
    await expect(option.locator(".version-badge")).toHaveText("LTS");
  }
  await page.goto("./zh/releases/?lts=1");
  await expect(page.locator(".release-row")).toHaveCount(4);
  await expect(page.locator(".release-row .version-warning")).toHaveCount(0);
  for (const family of expected) {
    const row = page
      .locator(".release-row")
      .filter({ hasText: "FFmpeg " + family.split(".")[0] + ".x" });
    await expect(row.locator(".version-badge")).toHaveText("LTS");
  }
  await page.goto("./zh/releases/4.4.8/");
  await expect(page.locator(".meta-line .version-badge")).toHaveText("LTS");
});

test("major entries lead directly to concrete version pages with related version links", async ({
  page,
  baseURL,
  request,
}) => {
  for (const lang of ["en", "zh"]) {
    await page.goto("./" + lang + "/releases/");
    const row = page.locator(".release-row").filter({ hasText: "FFmpeg 9.x" });
    await expect(row.locator(".release-row-target")).toHaveAttribute(
      "href",
      new URL(lang + "/releases/9.1/", baseURL).pathname,
    );
    await row.click();
    await expect(page).toHaveURL(baseURL + lang + "/releases/9.1/");
    await expect(page.locator("h1")).toHaveText("FFmpeg 9.1");
    await expect(
      page.locator(".major-version-choices,.page-head .version-warning"),
    ).toHaveCount(0);
    const related = page.locator("#history .release-row");
    await expect(related).toHaveCount(3);
    await expect(related.locator(".version-warning")).toHaveCount(3);
    await expect(
      related.locator(".release-row-target").first(),
    ).toHaveAttribute(
      "href",
      new URL(lang + "/releases/9.0.2/", baseURL).pathname,
    );
    await related.first().click();
    await expect(page).toHaveURL(baseURL + lang + "/releases/9.0.2/");
    await expect(page.locator("h1")).toHaveText("FFmpeg 9.0.2");
    await expect(
      page.locator("#history .release-row").filter({ hasText: "9.1" }),
    ).toHaveCount(1);
    await page.locator(".history-back").click();
    await expect(page).toHaveURL(baseURL + lang + "/releases/9.1/");
    const redirect = await request.get(baseURL + lang + "/releases/9.x/");
    expect(await redirect.text()).toContain('http-equiv="refresh"');
    expect(await redirect.text()).not.toContain("build-matrix");
    await page.goto("./" + lang + "/releases/9.x/?version=ffmpeg-9.0.2");
    await expect(page).toHaveURL(baseURL + lang + "/releases/9.0.2/");
    await page.goto("./" + lang + "/releases/9.x/");
    await expect(page).toHaveURL(baseURL + lang + "/releases/9.1/");
  }
  const sitemap = await request.get(baseURL + "sitemap.xml");
  expect(await sitemap.text()).not.toContain("/releases/9.x/");
});

test("version badges share adaptive positioning and do not change selection", async ({
  page,
}) => {
  for (const lang of ["en", "zh"]) {
    for (const width of [320, 390, 1280]) {
      await page.setViewportSize({ width, height: 640 });
      await page.goto("./" + lang + "/");
      const url = page.url();
      const badge = page.locator(".version-trigger-wrap > .version-badge");
      const tip = page.locator(".version-lts-popover");
      await badge.hover();
      await expect(tip).toBeVisible();
      await expect(tip).toContainText(
        lang === "zh" ? "长期支持" : "Long-term support",
      );
      const bounds = await tip.boundingBox();
      expect(bounds!.x).toBeGreaterThanOrEqual(11);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width - 11);
      expect(bounds!.y).toBeGreaterThanOrEqual(11);
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(629);
      await badge.click();
      await expect(tip).toBeVisible();
      await expect(page).toHaveURL(url);
      await expect(page.locator(".version-popup")).not.toBeVisible();
      await page.keyboard.press("Escape");
      await expect(tip).not.toBeVisible();
      await page.locator(".version-trigger").click();
      const popup = page.locator(".version-popup");
      const optionBadge = popup
        .locator(".version-option .version-badge")
        .first();
      await optionBadge.click();
      await expect(tip).toBeVisible();
      await expect(popup).toBeVisible();
      await expect(page).toHaveURL(url);
      await page.keyboard.press("Escape");
      await expect(tip).not.toBeVisible();
      await page.keyboard.press("Escape");
      await expect(popup).not.toBeVisible();
      await page.goto("./" + lang + "/releases/");
      const rowBadge = page.locator(".release-row .version-badge").first();
      const listUrl = page.url();
      await rowBadge.click();
      await expect(tip).toBeVisible();
      await expect(page).toHaveURL(listUrl);
      await page.locator("h1").hover();
      await expect(tip).not.toBeVisible();
    }
  }
});

test("theme dropdown aligns trigger edge and all option columns", async ({
  page,
}) => {
  for (const lang of ["en", "zh"]) {
    for (const width of [320, 390, 1280]) {
      await page.setViewportSize({ width, height: 640 });
      await page.goto("./" + lang + "/");
      const trigger = page.locator(".theme-menu summary");
      await trigger.click();
      const menu = page.locator(".theme-options");
      await expect(menu).toBeVisible();
      const a = (await trigger.boundingBox())!,
        b = (await menu.boundingBox())!;
      expect(Math.abs(a.x + a.width - b.x - b.width)).toBeLessThanOrEqual(1);
      expect(b.x).toBeGreaterThanOrEqual(0);
      expect(b.x + b.width).toBeLessThanOrEqual(width);
      const positions = await menu.locator("button").evaluateAll((rows) =>
        rows.map((row) => ({
          icon: row.querySelector("svg")!.getBoundingClientRect().left,
          label: row.querySelector("span")!.getBoundingClientRect().left,
        })),
      );
      for (const pos of positions) {
        expect(pos.icon).toBeCloseTo(positions[0].icon);
        expect(pos.label).toBeCloseTo(positions[0].label);
      }
      await menu.locator("button").last().click();
      await expect(menu).not.toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    }
  }
});

test("warning flips above the anchor near the viewport bottom", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 480 });
  await page.goto("./zh/releases/9.1/");
  const icon = page.locator(".release-row .version-warning").first();
  await icon.evaluate((node) => {
    const rect = node.getBoundingClientRect();
    window.scrollTo(0, window.scrollY + rect.bottom - (innerHeight - 24));
  });
  await icon.hover();
  const tip = page.locator(".version-warning-popover");
  await expect(tip).toBeVisible();
  await expect(tip).toHaveAttribute("data-side", "top");
  const a = (await icon.boundingBox())!,
    b = (await tip.boundingBox())!;
  expect(b.y + b.height).toBeLessThan(a.y);
  expect(b.x).toBeGreaterThanOrEqual(11);
  expect(b.x + b.width).toBeLessThanOrEqual(379);
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(tip).not.toBeVisible();
});

test("version picker shows exact build dates for default, filtered and historical options", async ({
  page,
}) => {
  const dates = new Map(entries.map((e) => [e.tag, e.date]));
  for (const lang of ["en", "zh"]) {
    for (const width of [320, 1280]) {
      await page.setViewportSize({ width, height: 800 });
      await page.goto("./" + lang + "/");
      await page.locator(".version-trigger").click();
      const popup = page.locator(".version-popup");
      const rows = popup.getByRole("option");
      const verify = async () => {
        await expect.poll(() => rows.count()).toBeGreaterThan(0);
        for (const row of await rows.all()) {
          const tag = (await row.getAttribute("data-tag"))!;
          const date = row.locator("time.version-option-date");
          await expect(date).toHaveText(dates.get(tag)!);
          await expect(date).toHaveAttribute("datetime", dates.get(tag)!);
          expect(
            await row.evaluate((n) => n.scrollWidth <= n.clientWidth + 1),
          ).toBe(true);
        }
      };
      await verify();
      await popup.locator('[data-filter="lts"]').click();
      await verify();
      await popup.locator('[data-filter="snapshot"]').click();
      await verify();
      await popup.locator('[data-filter="all"]').click();
      const old = entries.find((e) => e.upstream === "9.0.1")!;
      await popup.getByRole("combobox").fill(old.tag);
      await expect(rows).toHaveCount(1);
      await verify();
    }
  }
});
test("catalog search exposes every stable release instead of folded representatives", async ({
  page,
  baseURL,
}) => {
  const stable = entries.filter((e) => e.channel === "release");
  await page.goto("./en/releases/");
  const search = page.getByRole("searchbox"),
    rows = page.locator(".release-row");
  for (const major of new Set(stable.map((e) => e.upstream.split(".")[0]))) {
    const expected = stable.filter((e) => e.upstream.startsWith(major + "."));
    for (const q of [major, major + ".x"]) {
      await search.fill(q);
      await expect(rows).toHaveCount(expected.length);
      for (const entry of expected) {
        await expect(
          rows.locator(".release-row-target").filter({
            hasText: new RegExp(
              "^FFmpeg " + entry.upstream.replace(/\./g, "\\.") + "$",
            ),
          }),
        ).toHaveAttribute(
          "href",
          new URL("en/releases/" + entry.upstream + "/", baseURL).pathname,
        );
      }
    }
  }
  await search.fill("ffmpeg");
  await expect(rows).toHaveCount(stable.length);
  for (const entry of stable) {
    await search.fill(entry.tag);
    await expect(rows).toHaveCount(1);
    await expect(rows.locator(".release-row-target")).toHaveAttribute(
      "href",
      new URL("en/build/" + entry.tag + "/", baseURL).pathname,
    );
  }
  await search.fill("9.x");
  await page.locator('.version-filter-tag[data-filter="lts"]').click();
  await expect(rows).toHaveCount(
    stable.filter((e) => e.upstream.startsWith("9.") && e.lts).length,
  );
  await search.fill("");
  await expect(rows).toHaveCount(
    new Set(stable.filter((e) => e.lts).map((e) => e.upstream.split(".")[0]))
      .size,
  );
  await page.locator('.version-filter-tag[data-filter="all"]').click();
  await expect(rows).toHaveCount(
    new Set(stable.map((e) => e.upstream.split(".")[0])).size,
  );
  await expect(rows.locator(".version-warning")).toHaveCount(0);
});

test("static 404 has localized recovery navigation, themes and no missing assets", async ({
  page,
  baseURL,
  request,
}) => {
  for (const lang of ["en", "zh"]) {
    for (const width of [320, 1280]) {
      await page.setViewportSize({ width, height: 720 });
      await page.addInitScript(() => localStorage.setItem("theme", "dark"));
      const response = await page.goto(
        "./" + lang + "/build/nonexistent-build/",
      );
      expect(response!.status()).toBe(404);
      await expect(page.locator("html")).toHaveAttribute(
        "lang",
        lang === "zh" ? "zh-CN" : "en",
      );
      await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
      await expect(
        page.getByRole("heading", {
          name: lang === "zh" ? "页面不存在" : "Page not found",
          exact: true,
        }),
      ).toBeVisible();
      await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
        "content",
        "noindex",
      );
      expect(
        await page.evaluate(() =>
          [...document.styleSheets].some((s) => s.cssRules.length > 0),
        ),
      ).toBe(true);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      const url = page.url();
      await page
        .getByLabel(lang === "zh" ? "主题" : "Theme", { exact: true })
        .selectOption("light");
      await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
      expect(await page.evaluate(() => localStorage.getItem("theme"))).toBe(
        "light",
      );
      await page
        .getByRole("link", { name: lang === "zh" ? "EN" : "中文", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: lang === "zh" ? "Page not found" : "页面不存在",
          exact: true,
        }),
      ).toBeVisible();
      await expect(page).toHaveURL(url);
      await page
        .getByRole("link", {
          name: lang === "zh" ? "All versions" : "全部版本",
          exact: true,
        })
        .click();
      await expect(page).toHaveURL(
        baseURL + (lang === "zh" ? "en" : "zh") + "/releases/",
      );
    }
  }
  const html = await request.get(baseURL + "404.html");
  expect(await html.text()).not.toContain("entry.client-");
  expect(await html.text()).not.toContain('http-equiv="refresh"');
  const sitemap = await request.get(baseURL + "sitemap.xml");
  expect(await sitemap.text()).not.toContain("404.html");
  expect((await request.get(baseURL + "zh/%zz/")).status()).toBe(404);
});
test("404 recovery works without JavaScript", async ({ browser, baseURL }) => {
  const ctx = await browser.newContext({
    javaScriptEnabled: false,
    baseURL,
    colorScheme: "dark",
  });
  try {
    const page = await ctx.newPage();
    const response = await page.goto("./en/missing/");
    expect(response!.status()).toBe(404);
    await expect(
      page.getByRole("heading", { name: "Page not found" }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        [...document.styleSheets].some((s) => s.cssRules.length > 0),
      ),
    ).toBe(true);
    await page
      .getByRole("link", { name: "Back to download", exact: true })
      .click();
    await expect(page).toHaveURL(baseURL + "en/");
    await page.goto("./missing/");
    await page.getByRole("link", { name: "中文", exact: true }).click();
    await expect(page).toHaveURL(baseURL + "zh/");
  } finally {
    await ctx.close();
  }
});
