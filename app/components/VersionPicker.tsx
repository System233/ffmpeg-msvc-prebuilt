import { VersionWarning, LtsBadge } from "./VersionWarning";
import { VersionSearch } from "./VersionSearch";
import { OptionTooltip } from "./OptionTooltip";
import { optionMeaning } from "../lib/option-copy";
import { Combobox } from "@base-ui/react/combobox";
import { Check, ChevronDown } from "lucide-react";
import { useState } from "react";
import {
  filterVersionOptions,
  defaultVersionOptions,
  versionHeads,
  type VersionOption,
  type VersionFilter,
} from "../domain/catalog";
import { t, type Language } from "../i18n";

export function VersionPicker({
  options,
  value,
  onChange,
  lang,
}: {
  options: readonly VersionOption[];
  value: string;
  onChange: (value: string) => void;
  lang: Language;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<VersionFilter>("all");
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.tag === value);
  const label = t(lang, "versionPicker.version");
  const groups = [
    { channel: "release", label: t(lang, "versionPicker.stableVersions") },
    { channel: "master", label: t(lang, "nav.snapshots") },
  ] as const;
  const filtered = filterVersionOptions(options, filter, query);
  const latestTag = defaultVersionOptions(options)[0]?.tag;
  const currentTags = new Set(versionHeads(options).map((o) => o.tag));
  const display = (o: VersionOption) =>
    (o.channel === "master"
      ? t(lang, "versionPicker.snapshot", { version: o.upstream })
      : "FFmpeg " + o.upstream) +
    (!currentTags.has(o.tag) ? " · " + o.tag : "");
  const tags = options.map((o) => o.tag);
  return (
    <div className="field version-picker">
      <span className="field-label">{label}</span>
      <Combobox.Root<string>
        items={tags}
        filteredItems={filtered.map((o) => o.tag)}
        value={value}
        inputValue={query}
        open={open}
        autoHighlight
        itemToStringLabel={(tag) => {
          const o = options.find((o) => o.tag === tag);
          return o ? display(o) : tag;
        }}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            setQuery("");
            setFilter("all");
          }
        }}
        onInputValueChange={(q) => setQuery(q)}
        onValueChange={(v) => {
          if (v && v !== value) onChange(v);
        }}
      >
        <div className="version-trigger-wrap">
          <OptionTooltip text={optionMeaning(lang, "version")} disabled={open}>
            <Combobox.Trigger className="version-trigger" aria-label={label}>
              <span className="version-trigger-label">
                {selected ? display(selected) : label}
              </span>
              {selected && selected.lts && (
                <span
                  className="version-badge version-lts-space"
                  aria-hidden="true"
                >
                  LTS
                </span>
              )}
              {selected?.warning && (
                <span className="version-warning-space" aria-hidden="true" />
              )}
              <ChevronDown size={16} aria-hidden="true" />
            </Combobox.Trigger>
          </OptionTooltip>
          {selected?.lts && <LtsBadge lang={lang} />}
          <VersionWarning warning={!!selected?.warning} lang={lang} />
        </div>
        <Combobox.Portal>
          <Combobox.Positioner
            className="version-positioner"
            side="bottom"
            collisionAvoidance={{
              side: "flip",
              align: "shift",
              fallbackAxisSide: "none",
            }}
            sideOffset={6}
            align="start"
            collisionPadding={12}
          >
            <Combobox.Popup className="version-popup">
              <VersionSearch
                lang={lang}
                filter={filter}
                onFilterChange={setFilter}
                snapshots
              >
                <Combobox.Input
                  aria-label={t(lang, "versionPicker.searchVersions")}
                  placeholder={t(lang, "versionPicker.searchVersionOrTag")}
                />
              </VersionSearch>
              <div className="version-results">
                <Combobox.Empty className="version-empty">
                  {t(lang, "versionPicker.noMatchingVersions")}
                </Combobox.Empty>
                <Combobox.List className="version-list">
                  {groups.map((g) => {
                    const rows = filtered.filter(
                      (o) => o.channel === g.channel,
                    );
                    if (!rows.length) return null;
                    return (
                      <Combobox.Group key={g.channel}>
                        <Combobox.GroupLabel className="version-group-label">
                          {g.label}
                        </Combobox.GroupLabel>
                        {rows.map((o) => (
                          <Combobox.Item
                            className="version-option"
                            key={o.tag}
                            value={o.tag}
                            data-tag={o.tag}
                          >
                            <span className="version-option-main">
                              <span className="version-option-title">
                                {display(o)}
                              </span>
                              <time
                                className="version-option-date"
                                dateTime={o.date}
                                title={t(lang, "versionPicker.buildDate")}
                              >
                                {o.date}
                              </time>
                            </span>
                            {o.lts && <LtsBadge lang={lang} inOption />}
                            <VersionWarning
                              warning={o.warning}
                              lang={lang}
                              inOption
                            />
                            {o.tag === latestTag && o.channel === "release" && (
                              <span className="version-latest">
                                {t(lang, "versionPicker.latest")}
                              </span>
                            )}
                            <Combobox.ItemIndicator className="version-check">
                              <Check size={16} aria-hidden="true" />
                            </Combobox.ItemIndicator>
                          </Combobox.Item>
                        ))}
                      </Combobox.Group>
                    );
                  })}
                </Combobox.List>
              </div>
            </Combobox.Popup>
          </Combobox.Positioner>
        </Combobox.Portal>
      </Combobox.Root>
    </div>
  );
}
