import type { Language } from "../lib/i18n";
export function PackageNoteText({
  note,
  lang,
}: {
  note?: string;
  lang: Language;
}) {
  const separator = lang === "zh" ? "；" : "; ";
  const parts = note?.split(separator) ?? [];
  return parts.map((part, index) => {
    const space = part.indexOf(" ");
    return (
      <span className="package-note-item" key={part}>
        <strong className="package-note-name">{part.slice(0, space)}</strong>
        {part.slice(space)}
        {index < parts.length - 1 && separator}
      </span>
    );
  });
}
