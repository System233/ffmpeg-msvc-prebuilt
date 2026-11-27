import { Search } from "lucide-react";
import { OptionTooltip } from "./OptionTooltip";
import { optionMeaning } from "../lib/option-copy";
import type { ReactNode } from "react";
import type { VersionFilter } from "../domain/catalog";
import { t, type Language } from "../i18n";

export function VersionSearch({
  lang,
  filter,
  onFilterChange,
  snapshots = false,
  children,
}: {
  lang: Language;
  filter: VersionFilter;
  onFilterChange: (filter: VersionFilter) => void;
  snapshots?: boolean;
  children: ReactNode;
}) {
  const choices: { key: VersionFilter; label: string }[] = [
    { key: "all", label: t(lang, "versionSearch.all") },
    { key: "lts", label: "LTS" },
    ...(snapshots
      ? [
          {
            key: "snapshot" as const,
            label: t(lang, "versionSearch.snapshots"),
          },
        ]
      : []),
  ];
  return (
    <div className="version-search">
      <Search size={16} aria-hidden="true" className="version-search-icon" />
      {children}
      <div
        className="version-filter-tags"
        role="group"
        aria-label={t(lang, "versionSearch.versionFilter")}
      >
        {choices.map(({ key, label }) => (
          <OptionTooltip key={key} text={optionMeaning(lang, key)}>
            <button
              type="button"
              className="version-filter-tag"
              data-filter={key}
              aria-pressed={filter === key}
              onClick={() => onFilterChange(key)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") e.stopPropagation();
              }}
            >
              {label}
            </button>
          </OptionTooltip>
        ))}
      </div>
    </div>
  );
}
