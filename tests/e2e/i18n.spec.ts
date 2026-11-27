import { test, expect } from "@playwright/test";
test("canonical localized pages contain their own metadata and no duplicate English page", async ({
  request,
  baseURL,
}) => {
  const en = await request.get(baseURL!);
  const zh = await request.get(baseURL + "zh/");
  expect(await en.text()).toContain('<html lang="en"');
  expect(await zh.text()).toContain('<html lang="zh-CN"');
  expect(await zh.text()).toContain("Windows 下载");
  const legacy = await request.get(baseURL + "en/");
  const html = await legacy.text();
  expect(html).toContain('http-equiv="refresh"');
  expect(html).not.toContain("entry.client-");
  expect((await request.get(baseURL + "en/_.data")).status()).toBe(404);
  const sitemap = await request.get(baseURL + "sitemap.xml");
  expect(await sitemap.text()).not.toMatch(/<loc>[^<]*\/en\//);
});
test("legacy English URL redirects preserving query and fragment", async ({
  page,
  baseURL,
}) => {
  await page.goto("./en/?arch=x64#download");
  await expect(page).toHaveURL(baseURL + "?arch=x64#download");
  await page.getByRole("link", { name: "中文", exact: true }).click();
  await expect(page).toHaveURL(baseURL + "zh/?arch=x64#download");
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await page.getByRole("link", { name: "EN", exact: true }).click();
  await expect(page).toHaveURL(baseURL + "?arch=x64#download");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});
