import { VariantNotice } from "./VariantNotice";
import { PackageNoteText } from "./PackageNoteText";
import { describeAssets } from "../domain/assets";
import type { Variant } from "../domain/catalog";
import { type Language } from "../lib/i18n";
import { AssetLink, AssetInspector } from "./ui";
import { assetLabel, packageNote } from "../lib/asset-copy";
import { optionMeaning } from "../lib/option-copy";

type Props = {
  variant: Variant;
  linkage: string;
  tag: string;
  repo: string;
  lang: Language;
  label: string;
  date: string;
};

export function PackageDownloads({
  variant,
  linkage,
  tag,
  repo,
  lang,
  label,
  date,
}: Props) {
  const assets = describeAssets(variant, linkage);
  const note = packageNote(assets, lang);
  return (
    <>
      <div className="package-downloads">
        {assets.map((d) => (
          <AssetLink
            key={d.kind}
            primary={d.kind === "binary"}
            secondary={d.kind !== "binary"}
            tooltip={optionMeaning(lang, d.kind)}
            asset={d.asset}
            tag={tag}
            repo={repo}
            lang={lang}
          >
            {assetLabel(d.kind, lang, true)}
          </AssetLink>
        ))}
        <AssetInspector
          variant={variant}
          linkage={linkage}
          tag={tag}
          repo={repo}
          lang={lang}
          label={label}
          date={date}
        />
      </div>
      <VariantNotice note={variant.note} lang={lang} />
      {note && (
        <p className="package-note muted">
          <PackageNoteText note={note} lang={lang} />
        </p>
      )}
    </>
  );
}
