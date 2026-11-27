import { t, type Language } from "./i18n";

const meanings: Record<string, [string, string]> = {
  x64: [
    "For 64-bit Intel and AMD Windows applications.",
    "适用于 Intel 和 AMD 的 64 位 Windows 应用。",
  ],
  x86: [
    "For 32-bit x86 Windows applications.",
    "适用于 32 位 x86 Windows 应用。",
  ],
  arm64: [
    "For native 64-bit Windows on Arm applications.",
    "适用于原生 64 位 Windows on Arm 应用。",
  ],
  arm: [
    "For 32-bit Arm Windows applications.",
    "适用于 32 位 ARM Windows 应用。",
  ],
  shared: [
    "Includes DLLs, command-line tools and an SDK for dynamic linking.",
    "包含 DLL、命令行工具和用于动态链接的 SDK。",
  ],
  static: [
    "Contains standalone command-line tools without separate FFmpeg DLLs.",
    "提供无需独立 FFmpeg DLL 的命令行工具。",
  ],
  lgpl: [
    "Selects the LGPL build profile for applications requiring LGPL libraries.",
    "选择 LGPL 构建模式，适用于需要 LGPL 库的应用。",
  ],
  gpl: [
    "Enables GPL components such as x264 and x265 when available.",
    "启用 x264、x265 等可用的 GPL 组件。",
  ],
  nonfree: [
    "Includes nonfree components and is not redistributable.",
    "包含 Nonfree 组件，不可再分发。",
  ],
  all: [
    "Shows all matching release series and builds.",
    "显示所有匹配的版本系列及构建。",
  ],
  lts: [
    "Shows long-term support release series.",
    "仅显示长期支持（LTS）版本系列。",
  ],
  snapshot: [
    "Shows builds from recent upstream development commits.",
    "仅显示基于上游开发提交的快照构建。",
  ],
  version: [
    "Select the FFmpeg release or snapshot build to download.",
    "选择需要下载的 FFmpeg 发行版本或快照构建。",
  ],
  binary: [
    "Contains the command-line tools and, for Shared builds, the Release SDK.",
    "包含命令行工具，共享库构建还包含 Release SDK。",
  ],
  debug: [
    "Adds debug libraries and symbols to the matching Binary archive.",
    "为对应二进制包补充调试库和调试符号。",
  ],
  develop: [
    "Contains the complete legacy SDK with debug libraries and symbols.",
    "包含完整的旧版 SDK、调试库和调试符号。",
  ],
};
export function optionMeaning(lang: Language, value: string) {
  const pair = meanings[value];
  return pair ? t(lang, pair[0], pair[1]) : undefined;
}
