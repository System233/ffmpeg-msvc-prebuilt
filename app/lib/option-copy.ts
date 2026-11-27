import { t, type Language, hasMessage } from "../i18n";
export function optionMeaning(lang: Language, value: string) {
  const key = "option." + value;
  return hasMessage(key)
    ? t(lang, key as Extract<import("../i18n").MessageKey, `option.${string}`>)
    : undefined;
}
