import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useLocation,
  isRouteErrorResponse,
} from "react-router";
import { useEffect, useState, type ReactNode } from "react";
import { ErrorPage, type ErrorTheme } from "./components/ErrorPage";
import { type Language } from "./lib/i18n";
import "./styles.css";
const themeInit =
  "try{var t=localStorage.getItem('theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}";
export function Layout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const base = import.meta.env.BASE_URL;
  const zh = /^\/zh(?:\/|$)/.test(pathname);
  const path = (pathname.replace(/^\/(en|zh)(?=\/|$)/, "") || "/").replace(
    /\/?$/,
    "/",
  );
  const site = import.meta.env.VITE_SITE_URL;
  return (
    <html lang={zh ? "zh-CN" : "en"} suppressHydrationWarning>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
        <link rel="icon" href={base + "favicon.svg"} />
        <link rel="canonical" href={site + (zh ? "/zh" : "") + path} />
        <link rel="alternate" hrefLang="en" href={site + path} />
        <link rel="alternate" hrefLang="zh-CN" href={site + "/zh" + path} />
        <link rel="alternate" hrefLang="x-default" href={site + path} />
        <Meta />
        <Links />
      </head>
      <body>
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}
export default function App() {
  return <Outlet />;
}
export function ErrorBoundary({ error }: { error: unknown }) {
  const { pathname } = useLocation();
  const [lang, setLang] = useState<Language>(
    /^\/zh(?:\/|$)/.test(pathname) ? "zh" : "en",
  );
  const [theme, setTheme] = useState<ErrorTheme>("system");
  useEffect(() => {
    try {
      const value = localStorage.getItem("theme");
      if (value === "light" || value === "dark") setTheme(value);
    } catch {}
  }, []);
  function changeTheme(value: ErrorTheme) {
    setTheme(value);
    try {
      localStorage.setItem("theme", value);
    } catch {}
    if (value === "system")
      document.documentElement.removeAttribute("data-theme");
    else document.documentElement.dataset.theme = value;
  }
  function changeLanguage(value: Language) {
    setLang(value);
    document.documentElement.lang = value === "zh" ? "zh-CN" : "en";
  }
  return (
    <>
      <meta name="robots" content="noindex" />
      <ErrorPage
        lang={lang}
        base={import.meta.env.BASE_URL}
        repo={import.meta.env.VITE_GITHUB_REPO_URL}
        notFound={isRouteErrorResponse(error) && error.status === 404}
        theme={theme}
        onLanguageChange={changeLanguage}
        onThemeChange={changeTheme}
      />
    </>
  );
}
