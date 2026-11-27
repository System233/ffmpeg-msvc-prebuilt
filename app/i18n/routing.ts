import { language, defaultLanguage } from "./config";
export function stripLanguage(path: string) {
  return path.replace(/^\/(en|zh)(?=\/|$)/, "") || "/";
}
export function pathLanguage(path: string) {
  return language(/^\/(en|zh)(?=\/|$)/.exec(path)?.[1]);
}
export function localized(lang: string, path: string) {
  const prefix = language(lang) === defaultLanguage ? "" : "/zh";
  return prefix + (path.startsWith("/") ? path : "/" + path);
}
