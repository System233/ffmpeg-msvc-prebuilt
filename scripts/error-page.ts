import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ErrorPage } from "../app/components/ErrorPage";
import { base, repo } from "./site-config";

// Render the same recovery UI as the React error boundary, without a router
// manifest or hydration payload. GitHub Pages serves it at arbitrary URLs.
export function errorPage(stylesheets: string[]) {
  const markup = ["en", "zh"]
    .map((lang) =>
      renderToStaticMarkup(
        createElement(
          "div",
          { "data-error-language": lang, hidden: lang === "zh" },
          createElement(ErrorPage, {
            lang: lang === "zh" ? "zh" : "en",
            base,
            repo,
          }),
        ),
      ),
    )
    .join("");
  const js = String.raw`(()=>{
    const base=__BASE__;
    function setTheme(theme){
      if(theme==="light"||theme==="dark")document.documentElement.dataset.theme=theme;
      else document.documentElement.removeAttribute("data-theme");
      document.querySelectorAll("[data-error-theme]").forEach(n=>n.value=theme);
    }
    function setLanguage(lang){
      document.documentElement.lang=lang==="zh"?"zh-CN":"en";
      document.title=(lang==="zh"?"页面不存在":"Page not found")+" | FFmpeg MSVC";
      document.querySelectorAll("[data-error-language]").forEach(n=>n.hidden=n.dataset.errorLanguage!==lang);
    }
    let theme="system";
    try{const stored=localStorage.getItem("theme");if(stored==="light"||stored==="dark")theme=stored}catch{}
    setTheme(theme);
    const path=location.pathname.startsWith(base)?location.pathname.slice(base.length):"";
    setLanguage(/^zh(?:\/|$)/.test(path)?"zh":"en");
    document.addEventListener("click",e=>{
      const link=e.target.closest("[data-error-language-switch]");
      if(!link||e.button!==0||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;
      e.preventDefault();
      setLanguage(link.dataset.errorLanguageSwitch);
      document.querySelector('[data-error-language="'+link.dataset.errorLanguageSwitch+'"] [data-error-language-switch]')?.focus();
    });
    document.addEventListener("change",e=>{
      if(!e.target.matches("[data-error-theme]"))return;
      const theme=e.target.value;
      setTheme(theme);
      try{localStorage.setItem("theme",theme)}catch{}
    });
  })()`.replace("__BASE__", JSON.stringify(base).replace(/</g, "\\u003c"));
  const links = stylesheets
    .map((href) =>
      renderToStaticMarkup(createElement("link", { rel: "stylesheet", href })),
    )
    .join("");
  return (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Page not found | FFmpeg MSVC</title>' +
    renderToStaticMarkup(
      createElement("link", { rel: "icon", href: base + "favicon.svg" }),
    ) +
    links +
    "<noscript><style>.error-theme{display:none}</style></noscript></head><body>" +
    markup +
    "<script>" +
    js +
    "</script></body></html>"
  );
}
