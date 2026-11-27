export const languages = ["en", "zh"] as const;
export type Language = (typeof languages)[number];
export const defaultLanguage: Language = "en";
export const locale = { en: "en", zh: "zh-CN" } as const;
export function language(value?: string): Language {
  return value === "zh" ? "zh" : defaultLanguage;
}
export function alternateLanguage(lang: Language): Language {
  return lang === "zh" ? "en" : "zh";
}
