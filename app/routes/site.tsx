import { VersionWarningNotice } from "../components/VersionWarning";
import { Tooltip } from "@base-ui/react/tooltip";
import { SiteHistory } from "../lib/site-history";
import { Outlet, NavLink, useParams, useLocation, Link } from "react-router";
import { Github, Menu, Monitor, Sun, Moon, Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { language, t } from "../lib/i18n";
import { localized } from "../domain/catalog";
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
  const route = pathname.replace(/^\/(en|zh)(?=\/|$)/, "") || "/";
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
  const alternate = lang === "zh" ? "en" : "zh";
  const nav = [
    ["/", t(lang, "Download", "下载"), route === "/"],
    ["/releases/", t(lang, "All versions", "全部版本"), isRelease],
    ["/master/", t(lang, "Snapshots", "快照版本"), isMaster],
    ["/guide/", t(lang, "Docs", "文档"), isDocs],
  ] as const;
  const themes = [
    {
      value: "system" as const,
      label: t(lang, "System", "跟随系统"),
      Icon: Monitor,
    },
    { value: "light" as const, label: t(lang, "Light", "浅色"), Icon: Sun },
    { value: "dark" as const, label: t(lang, "Dark", "深色"), Icon: Moon },
  ];
  const ThemeIcon = themes.find((x) => x.value === theme)!.Icon;
  return (
    <>
      <a className="skip-link" href="#main-content">
        {t(lang, "Skip to content", "跳到主要内容")}
      </a>
      <header className="site-header">
        <div className="container nav">
          <Link className="brand" to={localized(lang, "/")}>
            FFmpeg <span>MSVC</span>
          </Link>
          <button
            className="icon-button mobile-menu"
            aria-label={t(lang, "Menu", "菜单")}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Menu size={20} />
          </button>
          <nav
            className={open ? "nav-links open" : "nav-links"}
            aria-label={t(lang, "Main navigation", "主导航")}
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
              {lang === "zh" ? "EN" : "中文"}
            </Link>
            <details ref={menu} className="theme-menu">
              <summary
                className="icon-button"
                aria-label={t(lang, "Theme", "主题")}
                title={t(lang, "Theme", "主题")}
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
        <a href={import.meta.env.BASE_URL + "data/index.json"}>Data V2 JSON</a>
        <a href={import.meta.env.VITE_GITHUB_REPO_URL}>GitHub</a>
      </footer>
    </>
  );
}
