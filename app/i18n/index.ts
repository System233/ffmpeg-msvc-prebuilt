import en, { type MessageKey } from "./messages/en";
import zh from "./messages/zh";
import { locale, type Language } from "./config";
export * from "./config";
export type { MessageKey };
const messages = { en, zh };
type Slots<S extends string> = S extends `${string}{${infer P}}${infer Rest}`
  ? P | Slots<Rest>
  : never;
type Args<K extends MessageKey> = [Slots<(typeof en)[K]>] extends [never]
  ? []
  : [Record<Slots<(typeof en)[K]>, string | number>];
export function hasMessage(key: string): key is MessageKey {
  return Object.hasOwn(en, key);
}
export function t<K extends MessageKey>(
  lang: Language,
  key: K,
  ...args: Args<K>
): string {
  const values = args[0] as Record<string, string | number> | undefined;
  return messages[lang][key].replace(/\{(\w+)\}/g, (_, name: string) => {
    if (!values || !Object.hasOwn(values, name))
      throw new Error("Missing translation parameter: " + key + "." + name);
    return String(values[name]);
  });
}
export function countLabel(
  lang: Language,
  key:
    | "releases.majorCount"
    | "releases.resultCount"
    | "common.variantCount"
    | "common.buildCount"
    | "common.snapshotCount",
  count: number,
) {
  const category =
    new Intl.PluralRules(locale[lang]).select(count) === "one"
      ? "one"
      : "other";
  return t(lang, `${key}.${category}`, {
    count: new Intl.NumberFormat(locale[lang]).format(count),
  });
}
export function linkageLabel(lang: Language, linkage: string, compact = false) {
  return t(
    lang,
    linkage === "shared"
      ? compact
        ? "linkage.sharedCompact"
        : "linkage.shared"
      : compact
        ? "linkage.staticCompact"
        : "linkage.static",
  );
}
