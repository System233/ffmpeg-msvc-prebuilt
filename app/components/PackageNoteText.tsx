import { t, type Language } from "../i18n";
import { assetLabel, type packageNotes } from "../lib/asset-copy";
export function PackageNoteText({
  note,
  lang,
}: {
  note?: ReturnType<typeof packageNotes>;
  lang: Language;
}) {
  return note?.map(({ kind, description }, index) => (
    <span className="package-note-item" key={kind}>
      <strong className="package-note-name">{assetLabel(kind, lang)}</strong>{" "}
      {description}
      {index < note.length - 1 && t(lang, "common.noteSeparator")}
    </span>
  ));
}
