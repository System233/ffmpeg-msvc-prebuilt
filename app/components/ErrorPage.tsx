import { ArrowLeft, ArrowRight, Github } from "lucide-react";
import { t, type Language } from "../lib/i18n";

export type ErrorTheme = "system" | "light" | "dark";

export function ErrorPage({
  lang,
  base,
  repo,
  notFound = true,
  theme = "system",
  onLanguageChange,
  onThemeChange,
}: {
  lang: Language;
  base: string;
  repo: string;
  notFound?: boolean;
  theme?: ErrorTheme;
  onLanguageChange?: (lang: Language) => void;
  onThemeChange?: (theme: ErrorTheme) => void;
}) {
  const href = (path: string) => base + lang + "/" + path;
  const alternate = lang === "zh" ? "en" : "zh";
  const mainId = "error-main-" + lang;
  return (
    <div className="error-page">
      <a className="skip-link" href={"#" + mainId}>
        {t(lang, "Skip to content", "跳到主要内容")}
      </a>
      <header className="site-header">
        <div className="container nav error-nav">
          <a className="brand" href={href("")}>
            FFmpeg <span>MSVC</span>
          </a>
          <div className="nav-actions">
            <a
              className="small-link"
              href={base + alternate + "/"}
              data-error-language-switch={alternate}
              onClick={
                onLanguageChange
                  ? (e) => {
                      e.preventDefault();
                      onLanguageChange(alternate);
                    }
                  : undefined
              }
            >
              {lang === "zh" ? "EN" : "中文"}
            </a>
            <select
              className="error-theme"
              aria-label={t(lang, "Theme", "主题")}
              data-error-theme=""
              value={onThemeChange ? theme : undefined}
              defaultValue={onThemeChange ? undefined : theme}
              onChange={
                onThemeChange
                  ? (e) => onThemeChange(e.target.value as ErrorTheme)
                  : undefined
              }
            >
              <option value="system">{t(lang, "System", "跟随系统")}</option>
              <option value="light">{t(lang, "Light", "浅色")}</option>
              <option value="dark">{t(lang, "Dark", "深色")}</option>
            </select>
            <a aria-label="GitHub" className="icon-button" href={repo}>
              <Github size={20} aria-hidden="true" />
            </a>
          </div>
        </div>
      </header>
      <main className="container main error-main" id={mainId}>
        <div className="error-content">
          {notFound && (
            <div className="error-code" aria-hidden="true">
              404
            </div>
          )}
          <h1>
            {notFound
              ? t(lang, "Page not found", "页面不存在")
              : t(lang, "Unable to load the page", "无法加载页面")}
          </h1>
          <p>
            {notFound
              ? t(
                  lang,
                  "This page does not exist or has moved. Browse the catalog to find the version you need.",
                  "此页面不存在或已迁移，请通过版本目录查找所需的构建。",
                )
              : t(
                  lang,
                  "The page could not be loaded. Return to the download page or browse the catalog.",
                  "页面加载失败，请返回下载首页或浏览版本目录。",
                )}
          </p>
          <div className="error-actions">
            <a className="hero-primary" href={href("")}>
              <ArrowLeft size={16} aria-hidden="true" />
              {t(lang, "Back to download", "返回下载首页")}
            </a>
            <a className="hero-secondary" href={href("releases/")}>
              {t(lang, "All versions", "全部版本")}
              <ArrowRight size={16} aria-hidden="true" />
            </a>
          </div>
          <nav
            className="error-links"
            aria-label={t(lang, "More resources", "其他入口")}
          >
            <a href={href("master/")}>{t(lang, "Snapshots", "快照版本")}</a>
            <a href={href("guide/")}>{t(lang, "Documentation", "使用文档")}</a>
          </nav>
        </div>
      </main>
      <footer className="container footer">
        <span>FFmpeg MSVC Prebuilt</span>
        <a href={base + "data/index.json"}>Release Catalog JSON</a>
        <a href={repo}>GitHub</a>
      </footer>
    </div>
  );
}
