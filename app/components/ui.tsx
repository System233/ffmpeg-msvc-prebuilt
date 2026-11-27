import { VariantNotice } from "./VariantNotice";
import { OptionTooltip } from "./OptionTooltip";
import { Check, Download, Copy, Info, X } from "lucide-react";
import { useEffect, useRef, useState, useId } from "react";
import type { ReactNode } from "react";
import type { Asset, Variant } from "../domain/catalog";
import { assetUrl, formatSize } from "../domain/catalog";
import { t, type Language } from "../lib/i18n";
import { describeAssets, type AssetKind } from "../domain/assets";
import {
  assetLabel,
  assetPurpose,
  assetContents,
  assetDependency,
} from "../lib/asset-copy";
export function Segments({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: {
    value: string;
    label: string;
    disabled?: boolean;
    tooltip?: string;
  }[];
  onChange: (v: string) => void;
}) {
  return (
    <fieldset className="field segments-field">
      <legend className="field-label">{label}</legend>
      <div className="segments">
        {options.map((o) => {
          const button = (
            <button
              type="button"
              aria-pressed={value === o.value}
              disabled={o.disabled}
              onClick={() => onChange(o.value)}
            >
              {o.label}
            </button>
          );
          return (
            <OptionTooltip key={o.value} text={o.tooltip}>
              {o.disabled && o.tooltip ? (
                <span className="disabled-segment-trigger">{button}</span>
              ) : (
                button
              )}
            </OptionTooltip>
          );
        })}
      </div>
    </fieldset>
  );
}
export function CopyButton({
  value,
  label,
  lang,
}: {
  value: string;
  label: string;
  lang: Language;
}) {
  const [status, setStatus] = useState<"idle" | "done" | "error">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  async function copy() {
    clearTimeout(timer.current);
    try {
      await navigator.clipboard.writeText(value);
      setStatus("done");
    } catch {
      setStatus("error");
    }
    timer.current = setTimeout(() => setStatus("idle"), 2000);
  }
  return (
    <span className="copy-control">
      <button
        className="icon-button"
        type="button"
        title={label}
        aria-label={label}
        onClick={copy}
      >
        {status === "done" ? <Check size={16} /> : <Copy size={16} />}
      </button>
      <span role="status" className="sr-only">
        {status === "done"
          ? t(lang, "Copied", "已复制")
          : status === "error"
            ? t(lang, "Copy failed", "复制失败")
            : ""}
      </span>
      {status === "error" && (
        <span className="copy-feedback" aria-hidden="true">
          {t(lang, "Copy failed", "复制失败")}
        </span>
      )}
    </span>
  );
}
export function AssetLink({
  asset,
  tag,
  repo,
  lang,
  children,
  primary = false,
  secondary = false,
  tooltip,
}: {
  asset: Asset;
  tag: string;
  repo: string;
  lang: Language;
  children?: ReactNode;
  primary?: boolean;
  secondary?: boolean;
  tooltip?: string;
}) {
  return (
    <OptionTooltip text={tooltip}>
      <a
        className={
          "download-link" +
          (primary ? " primary" : secondary ? " secondary" : "")
        }
        href={assetUrl(repo, tag, asset)}
        title={tooltip ? undefined : asset.file}
      >
        <Download size={15} aria-hidden="true" />
        <span>{children ?? t(lang, "Download", "下载")}</span>
        <span className="asset-size">{formatSize(asset.size)}</span>
        <span className="sr-only"> {asset.file}</span>
      </a>
    </OptionTooltip>
  );
}
type InfoProps = {
  linkage: string;
  initialKind?: AssetKind;
  variant: Variant;
  tag: string;
  repo: string;
  lang: Language;
  label: string;
  date: string;
};
export function AssetInspector({
  linkage,
  initialKind = "binary",
  variant,
  tag,
  repo,
  lang,
  label,
  date,
}: InfoProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const heading = useId();
  const [kind, setKind] = useState<AssetKind>(initialKind);
  const assets = describeAssets(variant, linkage);
  const selected = assets.find((d) => d.kind === kind) ?? assets[0];
  const asset = selected.asset;
  function open() {
    setKind(initialKind);
    dialog.current?.showModal();
  }
  function close() {
    dialog.current?.close();
  }
  const value = (name: string, content: string, copy = false) => (
    <div className="info-field">
      <div className="info-label">
        {name}
        {copy && (
          <CopyButton
            value={content}
            label={t(lang, "Copy ", "复制 ") + name}
            lang={lang}
          />
        )}
      </div>
      <code>{content}</code>
    </div>
  );
  return (
    <>
      <button
        ref={button}
        type="button"
        className="icon-button info-trigger"
        onClick={open}
        aria-label={
          t(lang, "Asset information: ", "产物信息：") +
          label +
          (initialKind === "binary"
            ? ""
            : " · " + assetLabel(initialKind, lang))
        }
        title={t(lang, "Checksums & build info", "校验和与构建信息")}
      >
        <Info size={17} />
      </button>
      <dialog
        ref={dialog}
        className="asset-dialog"
        aria-labelledby={heading}
        onClose={() => button.current?.focus({ preventScroll: true })}
        onClick={(e) => {
          if (e.target === e.currentTarget) close();
        }}
      >
        <section className="inspector">
          <header className="inspector-head">
            <div>
              <h2 id={heading}>{t(lang, "Asset information", "产物信息")}</h2>
              <p className="muted">{label}</p>
            </div>
            <button
              type="button"
              className="icon-button"
              aria-label={t(lang, "Close", "关闭")}
              onClick={close}
              autoFocus
            >
              <X size={20} />
            </button>
          </header>
          {assets.length > 1 && (
            <Segments
              label={t(lang, "Package", "产物类型")}
              value={selected.kind}
              options={assets.map((d) => ({
                value: d.kind,
                label: assetLabel(d.kind, lang),
              }))}
              onChange={(v) => setKind(v as AssetKind)}
            />
          )}
          <div className="inspector-purpose">
            <strong>{assetPurpose(selected, lang)}</strong>
            <p className="muted">{assetContents(selected, lang)}</p>
            {assetDependency(selected, lang) && (
              <p className="muted">{assetDependency(selected, lang)}</p>
            )}
            {selected.requiresBinary && (
              <a
                className="matching-binary"
                href={assetUrl(repo, tag, variant.binary)}
              >
                <Download size={15} aria-hidden="true" />
                {t(lang, "Matching Binary", "对应二进制")}
              </a>
            )}
          </div>
          <VariantNotice note={variant.note} lang={lang} />
          <div className="info-body">
            {value(t(lang, "Filename", "文件名"), asset.file, true)}
            {value(t(lang, "Size", "大小"), formatSize(asset.size))}
            {value("SHA-256", asset.sha256, true)}
            {value(
              t(lang, "Download URL", "下载地址"),
              assetUrl(repo, tag, asset),
              true,
            )}
            {variant.abi && value("ABI", variant.abi, true)}
            {variant.format !== undefined &&
              value(
                t(lang, "Package format", "打包格式"),
                String(variant.format),
              )}
            {value(t(lang, "Asset date", "资产日期"), variant.date ?? date)}
          </div>
        </section>
      </dialog>
    </>
  );
}
