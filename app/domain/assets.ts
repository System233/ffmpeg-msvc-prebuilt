import type { Asset, Variant } from "./catalog";
export type AssetKind = "binary" | "develop" | "debug";
export type AssetRole =
  "static-cli" | "release-sdk" | "legacy-sdk" | "debug-addon";
export type AssetDescriptor = {
  kind: AssetKind;
  role: AssetRole;
  asset: Asset;
  requiresBinary: boolean;
};
export function describeAssets(
  variant: Variant,
  linkage: string,
): AssetDescriptor[] {
  const binary: AssetDescriptor = {
    kind: "binary",
    role: linkage === "static" ? "static-cli" : "release-sdk",
    asset: variant.binary,
    requiresBinary: false,
  };
  if (variant.debug)
    return [
      binary,
      {
        kind: "debug",
        role: "debug-addon",
        asset: variant.debug,
        requiresBinary: true,
      },
    ];
  if (variant.develop)
    return [
      binary,
      {
        kind: "develop",
        role: "legacy-sdk",
        asset: variant.develop,
        requiresBinary: false,
      },
    ];
  return [binary];
}
export function validAssetSet(variant: Variant, linkage: string): boolean {
  if (variant.debug && variant.develop) return false;
  if ((variant.abi === undefined) !== (variant.format === undefined))
    return false;
  if (variant.format !== undefined && variant.format !== 2) return false;
  if (linkage === "static") return !variant.debug && !variant.develop;
  if (linkage !== "shared") return false;
  return variant.format === 2
    ? !!variant.debug && !variant.develop
    : !variant.debug;
}
