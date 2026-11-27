import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import en, { type MessageKey } from "../app/i18n/messages/en";
import zh from "../app/i18n/messages/zh";
import { t, countLabel, languages } from "../app/i18n";
import { localized, pathLanguage, stripLanguage } from "../app/i18n/routing";
import { loadFAQ, loadDocument } from "../app/content/markdown.server";
import {
  enumerateRoutes,
  enumerateLocalizedPages,
} from "../scripts/static-routes";
import { base } from "../scripts/site-config";

describe("translation contract", () => {
  it("requires matching keys and interpolation slots in both languages", () => {
    expect(Object.keys(zh).sort()).toEqual(Object.keys(en).sort());
    const slots = (value: string) =>
      [...value.matchAll(/\{(\w+)\}/g)].map((x) => x[1]).sort();
    for (const key of Object.keys(en) as MessageKey[]) {
      expect(zh[key].trim(), key).not.toBe("");
      expect(slots(zh[key]), key).toEqual(slots(en[key]));
    }
    expect(t("en", "build.backToVersion", { version: "9.1" })).toBe(
      "Back to FFmpeg 9.1",
    );
    expect(t("zh", "build.backToYear", { year: 2026 })).toBe(
      "返回 2026 年快照",
    );
    expect(countLabel("en", "releases.resultCount", 1)).toBe("1 result");
    expect(countLabel("en", "releases.resultCount", 2)).toBe("2 results");
    expect(countLabel("zh", "releases.resultCount", 2)).toBe("2 条结果");
  });
  it("keeps Chinese display copy out of UI source modules", () => {
    for (const root of ["app/components", "app/routes", "app/lib"]) {
      for (const file of readdirSync(root, { recursive: true }).filter((x) =>
        /\.tsx?$/.test(String(x)),
      )) {
        expect(
          readFileSync(root + "/" + file, "utf8"),
          String(file),
        ).not.toMatch(/\p{Script=Han}/u);
      }
    }
  });
});

describe("localized content and SSG", () => {
  it("enumerates exactly one canonical page per language", () => {
    const { index, shards } = JSON.parse(
      readFileSync(".generated/catalog.json", "utf8"),
    );
    const routes = enumerateRoutes(index, shards);
    const pages = enumerateLocalizedPages(routes);
    expect(new Set(pages).size).toBe(routes.length * languages.length);
    expect(pages).not.toContain("/en/");
    for (const path of routes)
      for (const lang of languages) {
        const target = localized(lang, path);
        expect(pages).toContain(target);
        expect(pathLanguage(target)).toBe(lang);
        expect(stripLanguage(target)).toBe(path);
      }
  });
  it("renders FAQ content and validates its localized documentation anchors", () => {
    const count = loadFAQ("en").length;
    expect(count).toBe(7);
    for (const lang of languages) {
      const faq = loadFAQ(lang);
      expect(faq).toHaveLength(count);
      expect(faq.map((x) => x.html).join("")).toContain(
        'class="hljs language-powershell"',
      );
      for (const { html } of faq) {
        for (const match of html.matchAll(/href="([^"]+)"/g)) {
          const url = new URL(match[1], "https://example.test" + base);
          if (url.origin !== "https://example.test") continue;
          const path = stripLanguage("/" + url.pathname.slice(base.length));
          const doc = path.split("/").filter(Boolean)[0];
          expect(url.hash).not.toBe("");
          expect(loadDocument(lang, doc).toc.map((x) => x.id)).toContain(
            decodeURIComponent(url.hash.slice(1)),
          );
        }
      }
    }
  });
});
