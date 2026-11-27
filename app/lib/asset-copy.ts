import type { AssetDescriptor, AssetKind } from "../domain/assets";
import { t, type Language } from "./i18n";
export function assetLabel(kind: AssetKind, lang: Language, _compact = false) {
  return kind === "binary"
    ? t(lang, "Binary", "二进制")
    : kind === "develop"
      ? t(lang, "Develop", "开发版")
      : t(lang, "Debug", "调试库");
}
export function assetPurpose(d: AssetDescriptor, lang: Language) {
  switch (d.role) {
    case "static-cli":
      return t(lang, "Standalone command-line tools", "独立命令行工具");
    case "release-sdk":
      return t(
        lang,
        "Runtime and complete Release SDK",
        "运行时与完整 Release SDK",
      );
    case "legacy-sdk":
      return t(
        lang,
        "Complete package with debug libraries and symbols",
        "含调试库和符号的完整包",
      );
    case "debug-addon":
      return t(
        lang,
        "Optional debug libraries and symbols",
        "可选调试库与符号",
      );
  }
}
export function assetContents(d: AssetDescriptor, lang: Language) {
  switch (d.role) {
    case "static-cli":
      return "EXE · " + t(lang, "Licenses", "许可证") + " · SBOM";
    case "release-sdk":
      return "EXE · DLL · Headers · LIB · CMake · pkg-config";
    case "legacy-sdk":
      return "EXE · DLL · Headers · LIB · PDB · debug/";
    case "debug-addon":
      return "bin/*.pdb · debug/bin/ · debug/lib/";
  }
}
export function assetDependency(d: AssetDescriptor, lang: Language) {
  return d.requiresBinary
    ? t(
        lang,
        "Requires matching Binary. Extract both archives into the same directory.",
        "需要对应的二进制包，将两个压缩包解压至同一目录。",
      )
    : undefined;
}
export function packageNote(
  assets: readonly AssetDescriptor[],
  lang: Language,
) {
  const roles = new Set(assets.map((a) => a.role));
  const parts: string[] = [];
  if (assets.some((a) => a.kind === "binary"))
    parts.push(
      roles.has("release-sdk")
        ? roles.has("static-cli")
          ? t(
              lang,
              "Binary includes executables (Shared also includes DLLs, headers and import libraries)",
              "二进制 包含可执行文件（共享库还包含 DLL、头文件及导入库）",
            )
          : t(
              lang,
              "Binary includes executables, DLLs, headers and import libraries",
              "二进制 包含可执行文件、DLL、头文件及导入库",
            )
        : t(
            lang,
            "Binary includes standalone executables",
            "二进制 包含独立可执行文件",
          ),
    );
  if (roles.has("legacy-sdk"))
    parts.push(
      t(
        lang,
        "Develop additionally includes debug libraries and PDBs",
        "开发版 还额外包含调试库和 PDB",
      ),
    );
  if (roles.has("debug-addon"))
    parts.push(
      t(
        lang,
        "Debug adds debug libraries and PDBs to the matching Binary",
        "调试库 包含调试库和 PDB，需解压至对应二进制目录",
      ),
    );
  return parts.length ? parts.join(lang === "zh" ? "；" : "; ") : undefined;
}
