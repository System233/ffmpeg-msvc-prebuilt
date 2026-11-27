export type Language = "en" | "zh";
export const language = (value?: string): Language =>
  value === "zh" ? "zh" : "en";
export const t = (lang: Language, en: string, zh: string) =>
  lang === "zh" ? zh : en;
export const linkageLabel = (
  lang: Language,
  linkage: string,
  compact = false,
) =>
  lang === "zh"
    ? linkage === "shared"
      ? "共享库"
      : "静态库"
    : compact
      ? linkage
      : linkage === "shared"
        ? "Shared"
        : "Static";
