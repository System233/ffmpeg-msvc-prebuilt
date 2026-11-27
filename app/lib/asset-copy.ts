import type { AssetDescriptor, AssetKind } from "../domain/assets";
import { t, type Language } from "../i18n";
export function assetLabel(kind: AssetKind, lang: Language, _compact = false) {
  return kind === "binary"
    ? t(lang, "package.binary")
    : kind === "develop"
      ? t(lang, "package.develop")
      : t(lang, "package.debug");
}
export function assetPurpose(d: AssetDescriptor, lang: Language) {
  switch (d.role) {
    case "static-cli":
      return t(lang, "package.staticCliPurpose");
    case "release-sdk":
      return t(lang, "package.releaseSdkPurpose");
    case "legacy-sdk":
      return t(lang, "package.legacySdkPurpose");
    case "debug-addon":
      return t(lang, "package.debugPurpose");
  }
}
export function assetContents(d: AssetDescriptor, lang: Language) {
  switch (d.role) {
    case "static-cli":
      return t(lang, "package.staticCliContents");
    case "release-sdk":
      return t(lang, "package.releaseSdkContents");
    case "legacy-sdk":
      return t(lang, "package.legacySdkContents");
    case "debug-addon":
      return t(lang, "package.debugContents");
  }
}
export function assetDependency(d: AssetDescriptor, lang: Language) {
  return d.requiresBinary ? t(lang, "package.debugDependency") : undefined;
}
export function packageNotes(
  assets: readonly AssetDescriptor[],
  lang: Language,
) {
  const roles = new Set(assets.map((a) => a.role));
  const parts: { kind: AssetKind; description: string }[] = [];
  if (assets.some((a) => a.kind === "binary"))
    parts.push({
      kind: "binary",
      description: roles.has("release-sdk")
        ? roles.has("static-cli")
          ? t(lang, "package.mixedBinaryNote")
          : t(lang, "package.sharedBinaryNote")
        : t(lang, "package.staticBinaryNote"),
    });
  if (roles.has("legacy-sdk"))
    parts.push({
      kind: "develop",
      description: t(lang, "package.developNote"),
    });
  if (roles.has("debug-addon"))
    parts.push({ kind: "debug", description: t(lang, "package.debugNote") });
  return parts.length ? parts : undefined;
}

export function packageNote(
  assets: readonly AssetDescriptor[],
  lang: Language,
) {
  return packageNotes(assets, lang)
    ?.map(({ kind, description }) => assetLabel(kind, lang) + " " + description)
    .join(t(lang, "common.noteSeparator"));
}
