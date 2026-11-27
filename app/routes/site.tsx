import { VersionWarningNotice } from "../components/VersionWarning";
import { Tooltip } from "@base-ui/react/tooltip";
import { SiteHistory } from "../lib/site-history";
import { Outlet, NavLink, useParams, useLocation, Link } from "react-router";
import { Github, Menu, Monitor, Sun, Moon, Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { stripLanguage } from "../i18n/routing";
import { alternateLanguage } from "../i18n";
import { language, t } from "../i18n";
import { localized } from "../i18n/routing";
type Theme = "system" | "light" | "dark";
export default function Site() {
  const lang = language(useParams().lang),
    { pathname, search, hash } = useLocation();
  const [theme, setTheme] = useState<Theme>("system"),
    [open, setOpen] = useState(false);
  const menu = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    try {
      const s = localStorage.getItem("theme");
      if (s === "light" || s === "dark") setTheme(s);
    } catch {}
  }, []);
  useEffect(() => {
    setOpen(false);
    if (menu.current) menu.current.open = false;
  }, [pathname]);
  useEffect(() => {
    function dismiss(e: PointerEvent) {
      if (menu.current && !menu.current.contains(e.target as Node))
        menu.current.open = false;
    }
    function escape(e: KeyboardEvent) {
      if (e.key === "Escape") {
        if (menu.current?.open) {
          menu.current.open = false;
          menu.current.querySelector("summary")?.focus();
        }
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  function changeTheme(next: Theme) {
    try {
      localStorage.setItem("theme", next);
    } catch {}
    if (next === "system")
      document.documentElement.removeAttribute("data-theme");
    else document.documentElement.dataset.theme = next;
    setTheme(next);
    if (menu.current) {
      menu.current.open = false;
      menu.current.querySelector("summary")?.focus();
    }
  }
  const route = stripLanguage(pathname);
  const isMaster =
    route.startsWith("/master") ||
    (route.startsWith("/build/") &&
      /\/build\/ffmpeg-(?:master|[^/]*-dev)/.test(route));
  const isRelease =
    route.startsWith("/releases") || (route.startsWith("/build/") && !isMaster);
  const isDocs =
    /^\/(guide|integration|packages|licenses|reference|self-build|history)(?:\/|$)/.test(
      route,
    );
  const alternate = alternateLanguage(lang);
  const nav = [
    ["/", t(lang, "common.download"), route === "/"],
    ["/releases/", t(lang, "nav.releases"), isRelease],
    ["/master/", t(lang, "nav.snapshots"), isMaster],
    ["/guide/", t(lang, "nav.docs"), isDocs],
  ] as const;
  const themes = [
    {
      value: "system" as const,
      label: t(lang, "theme.system"),
      Icon: Monitor,
    },
    { value: "light" as const, label: t(lang, "theme.light"), Icon: Sun },
    { value: "dark" as const, label: t(lang, "theme.dark"), Icon: Moon },
  ];
  const ThemeIcon = themes.find((x) => x.value === theme)!.Icon;
  return (
    <>
      <a className="skip-link" href="#main-content">
        {t(lang, "nav.skipToContent")}
      </a>
      <header className="site-header">
        <div className="container nav">
          <Link className="brand" to={localized(lang, "/")}>
            FFmpeg <span>MSVC</span>
          </Link>
          <button
            className="icon-button mobile-menu"
            aria-label={t(lang, "nav.menu")}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Menu size={20} />
          </button>
          <nav
            className={open ? "nav-links open" : "nav-links"}
            aria-label={t(lang, "nav.main")}
          >
            {nav.map(([path, label, active]) => (
              <Link
                key={path}
                className={active ? "active" : undefined}
                aria-current={active ? "page" : undefined}
                to={localized(lang, path)}
              >
                {label}
              </Link>
            ))}
          </nav>
          <div className="nav-actions">
            <Link
              to={localized(alternate, route) + search + hash}
              className="small-link"
            >
              {t(lang, "nav.languageSwitch")}
            </Link>
            <details ref={menu} className="theme-menu">
              <summary
                className="icon-button"
                aria-label={t(lang, "theme.label")}
                title={t(lang, "theme.label")}
              >
                <ThemeIcon size={18} />
              </summary>
              <div className="theme-options">
                {themes.map(({ value, label, Icon }) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={theme === value}
                    onClick={() => changeTheme(value)}
                  >
                    <Icon size={16} />
                    <span>{label}</span>
                    {theme === value && (
                      <Check className="theme-check" size={14} />
                    )}
                  </button>
                ))}
              </div>
            </details>
            <a
              aria-label="GitHub"
              className="icon-button"
              href={import.meta.env.VITE_GITHUB_REPO_URL}
            >
              <Github size={20} />
            </a>
          </div>
        </div>
      </header>
      <main id="main-content" className="container main">
        <SiteHistory>
          <Tooltip.Provider delay={350} closeDelay={0}>
            <Outlet />
          </Tooltip.Provider>
          <VersionWarningNotice key={pathname} lang={lang} />
        </SiteHistory>
      </main>
      <footer className="container footer">
        <span>FFmpeg MSVC Prebuilt</span>
        <a href={import.meta.env.BASE_URL + "data/index.json"}>
          {t(lang, "site.catalogJson")}
        </a>
        <a href={import.meta.env.VITE_GITHUB_REPO_URL}>GitHub</a>
      </footer>
    </>
  );
}
