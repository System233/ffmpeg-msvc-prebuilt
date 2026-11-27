import { ArrowLeft, ArrowRight, Github } from "lucide-react";
import { localized } from "../i18n/routing";
import { alternateLanguage, t, type Language } from "../i18n";

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
  const href = (path: string) => base + localized(lang, "/" + path).slice(1);
  const alternate = alternateLanguage(lang);
  const mainId = "error-main-" + lang;
  return (
    <div className="error-page">
      <a className="skip-link" href={"#" + mainId}>
        {t(lang, "nav.skipToContent")}
      </a>
      <header className="site-header">
        <div className="container nav error-nav">
          <a className="brand" href={href("")}>
            FFmpeg <span>MSVC</span>
          </a>
          <div className="nav-actions">
            <a
              className="small-link"
              href={base + localized(alternate, "/").slice(1)}
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
              {t(lang, "nav.languageSwitch")}
            </a>
            <select
              className="error-theme"
              aria-label={t(lang, "theme.label")}
              data-error-theme=""
              value={onThemeChange ? theme : undefined}
              defaultValue={onThemeChange ? undefined : theme}
              onChange={
                onThemeChange
                  ? (e) => onThemeChange(e.target.value as ErrorTheme)
                  : undefined
              }
            >
              <option value="system">{t(lang, "theme.system")}</option>
              <option value="light">{t(lang, "theme.light")}</option>
              <option value="dark">{t(lang, "theme.dark")}</option>
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
              ? t(lang, "errorPage.pageNotFound")
              : t(lang, "errorPage.unableToLoadThePage")}
          </h1>
          <p>
            {notFound
              ? t(lang, "error.notFoundDescription")
              : t(lang, "error.loadDescription")}
          </p>
          <div className="error-actions">
            <a className="hero-primary" href={href("")}>
              <ArrowLeft size={16} aria-hidden="true" />
              {t(lang, "errorPage.backToDownload")}
            </a>
            <a className="hero-secondary" href={href("releases/")}>
              {t(lang, "nav.releases")}
              <ArrowRight size={16} aria-hidden="true" />
            </a>
          </div>
          <nav
            className="error-links"
            aria-label={t(lang, "errorPage.moreResources")}
          >
            <a href={href("master/")}>{t(lang, "nav.snapshots")}</a>
            <a href={href("guide/")}>{t(lang, "nav.documentation")}</a>
          </nav>
        </div>
      </main>
      <footer className="container footer">
        <span>FFmpeg MSVC Prebuilt</span>
        <a href={base + "data/index.json"}>{t(lang, "site.catalogJson")}</a>
        <a href={repo}>GitHub</a>
      </footer>
    </div>
  );
}
