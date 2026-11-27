import { test, expect } from "@playwright/test";
test.skip(
  process.env.CATALOG_FIXTURE !== "1",
  "Synthetic native-format fixture only",
);
test("dated batch order, explicit sparse selection, reused filename and lazy loading", async ({
  page,
}) => {
  await page.goto("./");
  const first = page.locator("a.download-link").first();
  await expect(first).toHaveAttribute(
    "href",
    /ffmpeg-9\.1-261125R10\/ffmpeg-9\.1_x64-windows-shared-lgpl-261125\.zip$/,
  );
  await page
    .getByRole("group", { name: "Architecture" })
    .getByRole("button", { name: "ARM64", exact: true })
    .click();
  await expect(
    page
      .getByRole("group", { name: "License" })
      .getByRole("button", { name: "LGPL", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("a.download-link")).toHaveCount(0);
  await page
    .getByRole("button", { name: "ARM64 · static · GPL", exact: true })
    .click();
  await expect(first).toHaveAttribute(
    "href",
    /ffmpeg-9\.1-261125R10\/ffmpeg-9\.1_arm64-windows-static-gpl-261124\.zip$/,
  );
  await expect(page.locator("a.download-link")).toHaveCount(1);
  await page
    .getByRole("group", { name: "License" })
    .getByRole("button", { name: "NONFREE", exact: true })
    .click();
  await expect(page.locator("a.download-link")).toHaveCount(0);
  await page
    .getByRole("button", { name: "X64 · shared · NONFREE", exact: true })
    .click();
  await expect(first).toHaveAttribute("href", /x64-windows-shared-nonfree/);
  const request = page.waitForRequest((r) =>
    r.url().endsWith("/data/releases/8.1.3.json"),
  );
  await page.locator(".version-trigger").click();
  await page.locator('.version-option[data-tag="ffmpeg-8.1.3-r1"]').click();
  await request;
  await expect(page.locator("a.download-link")).toHaveCount(0);
  await page
    .getByRole("button", { name: "X86 · shared · GPL", exact: true })
    .click();
  await expect(first).toHaveAttribute(
    "href",
    /ffmpeg-8\.1\.3-r1\/ffmpeg-8\.1\.3-r1_x86-windows-shared-gpl\.zip$/,
  );
  await page.locator(".version-trigger").click();
  await page
    .locator('.version-option[data-tag="ffmpeg-master-261125R10"]')
    .click();
  await page
    .getByRole("button", { name: "X64 · shared · LGPL", exact: true })
    .click();
  await expect(first).toHaveAttribute("href", /ffmpeg-master-261125R10\//);
});
test("native metadata inspector and legacy links", async ({ page }) => {
  await page.goto("./en/releases/n8.1.3-r1.html");
  await expect(
    page.getByRole("heading", { name: "FFmpeg 8.1.3" }),
  ).toBeVisible();
  await page.goto("./en/build/ffmpeg-9.1-261125R10/");
  await page
    .getByRole("button", {
      name: "Asset information: X64 · shared · LGPL",
      exact: true,
    })
    .click();
  const d = page.getByRole("dialog");
  await expect(d.getByText("Package format", { exact: true })).toBeVisible();
  await expect(d.getByText("2", { exact: true })).toBeVisible();
  await expect(d.getByText("2026-11-25", { exact: true })).toBeVisible();
  await d.getByRole("button", { name: "Debug", exact: true }).click();
  await expect(
    d.getByText(
      "Requires matching Binary. Extract both archives into the same directory.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    d.getByText("ffmpeg-9.1_x64-windows-shared-lgpl-debug-261125.zip", {
      exact: true,
    }),
  ).toBeVisible();
  await d.getByRole("button", { name: "Close" }).click();
  await expect(
    page.getByRole("heading", { name: "NONFREE", exact: true }).first(),
  ).toBeVisible();
});

test("new debug add-on and legacy standalone package preserve their distinct semantics", async ({
  page,
}) => {
  await page.goto("./");
  await expect(page.locator(".package-downloads a.download-link")).toHaveCount(
    2,
  );
  await expect(
    page.locator('.package-downloads a.download-link[href*="-debug-"]'),
  ).toHaveCount(1);
  await expect(page.locator(".package-downloads .info-trigger")).toHaveCount(1);
  await page.locator(".package-downloads .info-trigger").click();
  const d = page.getByRole("dialog");
  await d.getByRole("button", { name: "Debug", exact: true }).click();
  await expect(
    d.getByText(
      "Requires matching Binary. Extract both archives into the same directory.",
      { exact: true },
    ),
  ).toBeVisible();
  await d.getByRole("button", { name: "Close" }).click();
  await page.locator(".version-trigger").click();
  await page.locator('.version-option[data-tag="ffmpeg-8.1.3-r1"]').click();
  await page
    .getByRole("button", { name: "X86 · shared · GPL", exact: true })
    .click();
  await expect(
    page.locator(".package-downloads a.download-link").last(),
  ).toContainText("Develop");
  await page.locator(".package-downloads .info-trigger").click();
  await d.getByRole("button", { name: "Develop", exact: true }).click();
  await expect(
    d.getByText("Complete package with debug libraries and symbols", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    d.getByText("Standalone archive; no separate Binary required.", {
      exact: true,
    }),
  ).toHaveCount(0);
});

test("full native matrix and historical Develop package", async ({ page }) => {
  await page.goto("./en/build/ffmpeg-9.0.2-261125/");
  await expect(page.locator(".matrix-actions a.download-link")).toHaveCount(24);
  await expect(page.locator(".matrix-actions .primary")).toHaveCount(0);
  await expect(page.locator(".matrix-actions .secondary")).toHaveCount(0);
  await expect(page.locator(".matrix-note > span:visible")).toHaveCount(1);
  await expect(page.locator(".matrix-note > span:visible")).toContainText(
    "Debug adds debug libraries and PDBs to the matching Binary",
  );
  await expect(page.locator(".license-note")).toHaveCount(0);
  await expect(
    page
      .locator(".matrix-actions a.download-link")
      .filter({ hasText: /Debug|Develop/ }),
  ).toHaveCount(8);
  const trigger = page.getByRole("button", {
    name: "Asset information: X64 · shared · LGPL",
    exact: true,
  });
  await trigger.click();
  const d = page.getByRole("dialog");
  const hash = () =>
    d
      .locator(".info-field")
      .filter({ has: page.getByText("SHA-256", { exact: true }) })
      .locator("code")
      .textContent();
  const binaryHash = await hash();
  await d.getByRole("button", { name: "Debug", exact: true }).click();
  expect(await hash()).not.toBe(binaryHash);
  await expect(
    d.getByRole("link", { name: "Matching Binary", exact: true }),
  ).toHaveAttribute(
    "href",
    /ffmpeg-9\.0\.2-261125\/ffmpeg-9\.0\.2_x64-windows-shared-lgpl-261125\.zip$/,
  );
  await d.getByRole("button", { name: "Close" }).click();
  await page.goto("./en/build/ffmpeg-8.1.3-r1/");
  const oldLinks = page
    .locator(".matrix-actions a.download-link")
    .filter({ hasText: /Debug|Develop/ });
  await expect(oldLinks).toHaveCount(2);
  for (const link of await oldLinks.all()) {
    await expect(link).toContainText("Develop");
    await expect(link).toHaveAttribute("href", /-develop(?:-|\.zip)/);
  }
  await expect(page.locator(".matrix-note > span:visible")).toHaveText(
    "Binary includes executables, DLLs, headers and import libraries; Develop additionally includes debug libraries and PDBs",
  );
});

test("Binary and optional Debug share one row with clear default hierarchy", async ({
  page,
}) => {
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("./en/");
      const links = page.locator(".package-downloads > a.download-link");
      await expect(links).toHaveCount(2);
      const metrics = await links.evaluateAll((items) =>
        items.map((el) => {
          const s = getComputedStyle(el),
            r = el.getBoundingClientRect();
          return {
            top: r.top,
            bottom: r.bottom,
            width: r.width,
            style: [
              s.backgroundColor,
              s.color,
              s.fontWeight,
              s.fontSize,
              s.padding,
              s.borderRadius,
            ],
          };
        }),
      );
      expect(metrics[0].style[0]).not.toEqual(metrics[1].style[0]);
      expect(metrics[1].style[0]).toBe("rgba(0, 0, 0, 0)");
      await expect(links.first()).toHaveClass(/primary/);
      await expect(links.last()).toHaveClass(/secondary/);
      expect(metrics[0].top).toBe(metrics[1].top);
      expect(metrics[0].bottom).toBe(metrics[1].bottom);
      expect(metrics[0].width).toBeGreaterThan(metrics[1].width);
      await expect(links.first()).toContainText("Binary");
      await expect(links.last()).toContainText("Debug");
      expect(
        await links.evaluateAll((items) =>
          items.every((el) => el.scrollWidth <= el.clientWidth + 1),
        ),
      ).toBe(true);
      await expect(
        page.locator(".package-downloads .info-trigger"),
      ).toHaveCount(1);
      await expect(page.locator(".fixture-notice")).toHaveCount(0);
      await expect(page.locator(".package-note")).toHaveCount(1);
      await expect(page.locator(".package-note")).toContainText(
        "Debug adds debug libraries and PDBs to the matching Binary",
      );
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(
        await page.evaluate(() => document.documentElement.clientWidth),
      );
    }
  }
  await page.goto("./en/build/ffmpeg-9.0.2-261125/");
  const styles = await page
    .locator(".matrix-cell:visible")
    .first()
    .locator("a.download-link")
    .evaluateAll((items) =>
      items.map((el) => {
        const s = getComputedStyle(el);
        return {
          color: s.color,
          weight: s.fontWeight,
          background: s.backgroundColor,
          padding: s.padding,
        };
      }),
    );
  expect(styles).toHaveLength(2);
  expect(styles[0]).toEqual(styles[1]);
  expect(styles[1].background).toBe("rgba(0, 0, 0, 0)");
});

test("visible packages always have one concise localized note", async ({
  page,
}) => {
  for (const lang of ["en", "zh"]) {
    const zh = lang === "zh";
    const nativeMatrix = zh
      ? "二进制 包含可执行文件（共享库还包含 DLL、头文件及导入库）；调试库 包含调试库和 PDB，需解压至对应二进制目录"
      : "Binary includes executables (Shared also includes DLLs, headers and import libraries); Debug adds debug libraries and PDBs to the matching Binary";
    const shared = zh
      ? "二进制 包含可执行文件、DLL、头文件及导入库；调试库 包含调试库和 PDB，需解压至对应二进制目录"
      : "Binary includes executables, DLLs, headers and import libraries; Debug adds debug libraries and PDBs to the matching Binary";
    const legacy = zh
      ? "二进制 包含可执行文件、DLL、头文件及导入库；开发版 还额外包含调试库和 PDB"
      : "Binary includes executables, DLLs, headers and import libraries; Develop additionally includes debug libraries and PDBs";
    const cli = zh
      ? "二进制 包含独立可执行文件"
      : "Binary includes standalone executables";
    for (const width of [1440, 1024, 820, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("./" + lang + "/build/ffmpeg-9.0.2-261125/");
      await expect(
        page.locator(".matrix-actions .primary,.matrix-actions .secondary"),
      ).toHaveCount(0);
      await expect(page.locator(".matrix-note > span:visible")).toHaveText(
        nativeMatrix,
      );
      await expect(page.locator(".license-note")).toHaveCount(0);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(
        await page.evaluate(() => document.documentElement.clientWidth),
      );
    }
    await page.goto("./" + lang + "/build/ffmpeg-8.1.3-r1/");
    await expect(page.locator(".matrix-note > span:visible")).toHaveText(
      legacy,
    );
    await page.goto("./" + lang + "/build/ffmpeg-9.1-261125R10/?arch=arm64");
    await expect(page.locator(".matrix-note > span:visible")).toHaveText(cli);
    await page.goto(
      "./" +
        lang +
        "/?version=ffmpeg-9.1-261125R10&arch=arm64&linkage=static&license=gpl",
    );
    await expect(
      page.locator(".package-downloads a.download-link"),
    ).toHaveCount(1);
    await expect(page.locator(".package-note")).toHaveText(cli);
    await page.goto("./" + lang + "/");
    await expect(page.locator(".package-note")).toHaveText(shared);
    const items = page.locator(".package-note .package-note-item");
    await expect(items).toHaveCount(2);
    await expect(items.locator(".package-note-dot")).toHaveCount(0);
    expect(
      await items.evaluateAll((nodes) =>
        nodes.every((n) => getComputedStyle(n).display === "inline"),
      ),
    ).toBe(true);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("./" + lang + "/build/ffmpeg-9.0.2-261125/");
    const dots = await page
      .locator(".matrix-note > span:visible .package-note-name")
      .evaluateAll((nodes) => nodes.map((n) => n.getBoundingClientRect().top));
    expect(dots).toHaveLength(2);
    expect(dots[1]).toBe(dots[0]);
    await page.goto("./" + lang + "/");
    await expect(page.locator(".package-note strong")).toHaveText(
      zh ? ["二进制", "调试库"] : ["Binary", "Debug"],
    );
  }
});

test("LTS display and filter follow explicit catalog metadata", async ({
  page,
}) => {
  await page.goto("./en/");
  await expect(page.locator(".version-trigger .version-badge")).toHaveCount(0);
  await page.locator(".version-trigger").click();
  const popup = page.locator(".version-popup");
  await page.locator('.version-filter-tag[data-filter="lts"]').click();
  const rows = popup.getByRole("option");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("9.0.2");
  await expect(rows.first()).toContainText("LTS");
  await rows.first().click();
  await expect(page.locator(".version-trigger .version-badge")).toHaveText(
    "LTS",
  );
  await page.goto("./en/releases/");
  await page.locator('.version-filter-tag[data-filter="lts"]').click();
  await expect(page.locator(".release-row")).toHaveCount(1);
  await expect(page.locator(".release-row").first()).toContainText("9.0.2");
});

test("major catalog keeps Latest and an independent LTS and exact historical tags", async ({
  page,
  baseURL,
}) => {
  await page.goto("./en/");
  await page.locator(".version-trigger").click();
  const popup = page.locator(".version-popup"),
    search = popup.getByRole("combobox");
  await expect(popup.getByRole("option")).toHaveCount(4);
  await expect(
    popup.locator('[data-tag="ffmpeg-9.1-261125R10"]'),
  ).toBeVisible();
  await expect(popup.locator('[data-tag="ffmpeg-9.0.2-261125"]')).toBeVisible();
  await expect(popup.locator('[data-tag="ffmpeg-9.1-261125R2"]')).toHaveCount(
    0,
  );
  await search.fill("ffmpeg-9.1-261125R2");
  await expect(popup.getByRole("option")).toHaveCount(1);
  await popup.getByRole("option").click();
  await expect(page.locator("a.download-link").first()).toHaveAttribute(
    "href",
    /ffmpeg-9\.1-261125R2\//,
  );
  await page.reload();
  await expect(page.locator("a.download-link").first()).toHaveAttribute(
    "href",
    /ffmpeg-9\.1-261125R2\//,
  );
  await page.goto("./en/releases/");
  await expect(page.locator(".release-row")).toHaveCount(2);
  const major = page.locator(".release-row").filter({ hasText: "FFmpeg 9.x" });
  await expect(major).toContainText("9.1");
  await expect(major).toContainText("9.0.2");
  await major.click();
  await expect(page).toHaveURL(baseURL + "en/releases/9.1/");
  await expect(page.locator("a.download-link").first()).toHaveAttribute(
    "href",
    /ffmpeg-9\.1-261125R10\//,
  );
  await expect(page.locator("#history .release-row")).toHaveCount(1);
  await expect(page.locator("#builds .release-row")).toHaveCount(2);
  await expect(
    page.locator("#builds .release-row-target").first(),
  ).toHaveAttribute("href", /\/build\/ffmpeg-9\.1-261125R2\//);
  await expect(page.locator(".build-section > .variant-notice")).toHaveCount(0);
  await page
    .locator("#history .release-row")
    .filter({ hasText: "9.0.2" })
    .click();
  await expect(page).toHaveURL(baseURL + "en/releases/9.0.2/");
  await expect(page.locator("a.download-link").first()).toHaveAttribute(
    "href",
    /ffmpeg-9\.0\.2-261125\//,
  );
  await page.reload();
  await expect(page.locator("a.download-link").first()).toHaveAttribute(
    "href",
    /ffmpeg-9\.0\.2-261125\//,
  );
  await page.goto("./en/releases/?lts=1");
  await page.locator(".release-row").first().click();
  await expect(page.locator("a.download-link").first()).toHaveAttribute(
    "href",
    /ffmpeg-9\.0\.2-261125\//,
  );
  await expect(page).toHaveURL(baseURL + "en/releases/9.0.2/");
  await page.goto("./en/releases/9.x/?version=ffmpeg-9.1-261125R2");
  await expect(page).toHaveURL(baseURL + "en/build/ffmpeg-9.1-261125R2/");
  await page.goto("./en/releases/?q=ffmpeg-9.1-261125R2");
  await page.locator(".release-row").first().click();
  await expect(page).toHaveURL(baseURL + "en/build/ffmpeg-9.1-261125R2/");
  await page.goto("./en/?version=missing-tag");
  await expect(page.locator("a.download-link")).toHaveCount(0);
  await page.getByRole("button", { name: "Select latest" }).click();
  await expect(page.locator("a.download-link").first()).toHaveAttribute(
    "href",
    /ffmpeg-9\.1-261125R10\//,
  );
});

test("catalog search reveals older batches and the picker displays batch dates", async ({
  page,
  baseURL,
}) => {
  await page.goto("./en/");
  await page.locator(".version-trigger").click();
  const popup = page.locator(".version-popup");
  await expect(
    popup.locator('[data-tag="ffmpeg-9.1-261125R10"] time'),
  ).toHaveText("2026-11-25");
  await popup.getByRole("combobox").fill("ffmpeg-9.1-261125R2");
  await expect(
    popup.locator('[data-tag="ffmpeg-9.1-261125R2"] time'),
  ).toHaveText("2026-11-25");
  await page.goto("./en/releases/");
  const search = page.getByRole("searchbox"),
    rows = page.locator(".release-row");
  await search.fill("9.x");
  await expect(rows).toHaveCount(4);
  await search.fill("9.1");
  await expect(rows).toHaveCount(3);
  await expect(rows.locator('a[href$="/releases/9.1/"]')).toHaveCount(1);
  await expect(
    rows.locator('a[href$="/build/ffmpeg-9.1-261125R2/"]'),
  ).toHaveCount(1);
  await search.fill("ffmpeg-9.1-261125r");
  await expect(rows).toHaveCount(2);
  await rows.locator('a[href$="/build/ffmpeg-9.1-261125R2/"]').click();
  await expect(page).toHaveURL(baseURL + "en/build/ffmpeg-9.1-261125R2/");
});
