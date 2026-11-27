import { HighlightedCode } from "./HighlightedCode";
import { Link } from "react-router";
import { ArrowUpRight, ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { localized } from "../domain/catalog";
import { t, type Language } from "../lib/i18n";

export function HomeFAQ({ lang }: { lang: Language }) {
  const zh = lang === "zh";
  const doc = (
    page: "guide" | "integration" | "packages" | "licenses" | "reference",
    en: string,
    cn: string,
    label: string,
  ) => (
    <>
      {zh && " "}
      <Link to={localized(lang, "/" + page + "/") + "#" + (zh ? cn : en)}>
        {label}
      </Link>
    </>
  );
  const questions: { q: string; answer: ReactNode }[] = [
    {
      q: t(
        lang,
        "Which FFmpeg version should I choose?",
        "如何选择 FFmpeg 版本？",
      ),
      answer: zh ? (
        <>
          <p>
            首次使用建议选择最新稳定版本的共享库
            二进制包。需要与已有项目保持兼容时，应选择项目要求的 FFmpeg
            主版本或具体版本，不要仅凭版本号越新越好。
          </p>
          <ul>
            <li>
              <strong>稳定版本：</strong>
              适合日常使用、生产部署及需要固定版本的项目。
            </li>
            <li>
              <strong>LTS：</strong>
              适合需要长期支持系列的项目，建议选择该系列最新可用补丁版本；LTS
              标记为本项目的版本系列分类，不代表上游仍在维护。
            </li>
            <li>
              <strong>快照版本：</strong>
              用于体验上游最新功能或修复，接口及行为可能变化。
            </li>
          </ul>
          <p>
            架构应与运行环境或目标程序匹配：常见 Intel/AMD 64 位 Windows 选择
            x64，原生 Windows on Arm 选择 ARM64；仅在目标程序确实需要 32
            位库时选择 x86 或 ARM。完整选项见
            {doc("guide", "quick-start", "快速开始", "快速开始")}。
          </p>
        </>
      ) : (
        <>
          <p>
            For a new installation, start with Shared Binary from the latest
            release. For an existing application, match its required FFmpeg
            major or exact version rather than upgrading blindly.
          </p>
          <ul>
            <li>
              <strong>Stable versions:</strong> for daily use, production and
              reproducible deployments.
            </li>
            <li>
              <strong>LTS:</strong> use the newest available patch in the
              required long-term support family. The label is a catalog
              classification and does not guarantee current upstream
              maintenance.
            </li>
            <li>
              <strong>Snapshots:</strong> for recent upstream features and
              fixes; APIs and behavior may change.
            </li>
          </ul>
          <p>
            Match the architecture to the target: x64 for typical 64-bit
            Intel/AMD Windows, ARM64 for native Windows on Arm, and x86 or ARM
            only when a 32-bit target requires it. See the{" "}
            {doc("guide", "quick-start", "快速开始", "quick start")} for all
            build options.
          </p>
        </>
      ),
    },
    {
      q: t(
        lang,
        "What is the difference between Shared and Static?",
        "共享库和静态库有什么区别？",
      ),
      answer: zh ? (
        <>
          <p>一般选择共享库。静态库适用于需要独立可执行文件的场景。</p>
          <ul>
            <li>
              <strong>共享库（推荐）：</strong>
              包含可执行文件、DLL、头文件与导入库。运行时应保留匹配的
              DLL，开发时使用对应头文件和 .lib。
            </li>
            <li>
              <strong>静态库：</strong>解压即可运行 ffmpeg.exe、ffprobe.exe
              等独立程序，无需另外携带 FFmpeg DLL；不包含供应用链接的 SDK。
            </li>
          </ul>
          <p>
            完整静态 SDK
            包含大量第三方静态库，体积过大，因此仅分发命令行工具；如需静态链接开发，请自行构建。参见
            {doc("guide", "which-one-to-pick", "如何选择", "构建产物选择表")} 与
            {doc(
              "integration",
              "prerequisites",
              "前置条件",
              "开发集成前置条件",
            )}
            。
          </p>
        </>
      ) : (
        <>
          <p>
            Shared is the usual choice. Static is intended for single-executable
            deployments.
          </p>
          <ul>
            <li>
              <strong>Shared (recommended):</strong> includes executables, DLLs,
              headers and import libraries. Keep the matching DLLs at runtime
              and use the corresponding headers and .lib files when compiling.
            </li>
            <li>
              <strong>Static:</strong> executables such as ffmpeg.exe and
              ffprobe.exe do not need separate FFmpeg DLLs. No
              application-linkable SDK is included.
            </li>
          </ul>
          <p>
            A complete static SDK would include many third-party static
            libraries and be too large to distribute. Build from source for
            static linking. See the{" "}
            {doc(
              "guide",
              "which-one-to-pick",
              "如何选择",
              "package selection table",
            )}{" "}
            and{" "}
            {doc(
              "integration",
              "prerequisites",
              "前置条件",
              "integration prerequisites",
            )}
            .
          </p>
        </>
      ),
    },
    {
      q: t(
        lang,
        "What is the difference between GPL and LGPL?",
        "GPL 和 LGPL 有什么区别？",
      ),
      answer: zh ? (
        <>
          <p>GPL 构建提供更多可选组件，LGPL 构建适用于需要 LGPL 库的项目。</p>
          <ul>
            <li>
              <strong>GPL：</strong>可包含 x264、x265 等 GPL
              编码器，适合需要这些编码功能的场景。
            </li>
            <li>
              <strong>LGPL：</strong>新版构建限制 GPL 组件；历史 LGPL
              构建存在已披露的许可证风险。
            </li>
          </ul>
          <p>
            可运行 <code>ffmpeg -encoders</code>{" "}
            确认所需编码器是否存在。构建产物包含对应的许可证、版权声明和依赖信息。详见
            {doc(
              "licenses",
              "choosing-a-license",
              "选择许可证",
              "许可证与再分发",
            )}
            。
          </p>
        </>
      ) : (
        <>
          <p>
            GPL builds offer more optional components; LGPL builds suit projects
            that require LGPL libraries.
          </p>
          <ul>
            <li>
              <strong>GPL:</strong> may include GPL encoders such as x264 and
              x265, for workflows that require those encoders.
            </li>
            <li>
              <strong>LGPL:</strong> updated builds restrict GPL components;
              historical LGPL builds have disclosed licensing risks.
            </li>
          </ul>
          <p>
            Run <code>ffmpeg -encoders</code> to check for required encoders.
            The archives include license notices and dependency information. See{" "}
            {doc(
              "licenses",
              "choosing-a-license",
              "选择许可证",
              "licenses and redistribution",
            )}
            .
          </p>
        </>
      ),
    },
    {
      q: t(lang, "How do I install and use FFmpeg?", "如何安装和使用 FFmpeg？"),
      answer: zh ? (
        <>
          <p>解压二进制包并配置 PATH 后，即可在终端使用 FFmpeg。</p>
          <ol>
            <li>
              优先下载共享库二进制 ZIP，解压至固定目录，例如{" "}
              <code>C:\Tools\ffmpeg</code>。
            </li>
            <li>
              找到 ffmpeg.exe 所在目录。共享库通常位于 <code>bin</code>；静态库
              通常位于解压根目录。
            </li>
            <li>将该目录加入 Windows 用户 PATH，重新打开终端。</li>
          </ol>
          <pre>
            <HighlightedCode
              language="powershell"
              code={
                "ffmpeg -version\nffprobe -hide_banner input.mp4\nffmpeg -i input.mp4 output.mkv"
              }
            />
          </pre>
          <p>
            上述命令依次验证安装、检查媒体信息及转码。共享库
            构建请保留同目录下匹配的 DLL。若不修改
            PATH，也可直接从可执行文件所在目录运行。参见
            {doc(
              "guide",
              "installation-and-first-commands",
              "安装与基本命令",
              "安装与基本命令",
            )}
            。
          </p>
        </>
      ) : (
        <>
          <p>
            Extract the binary archive and add its executable directory to PATH
            to run FFmpeg from a terminal.
          </p>
          <ol>
            <li>
              Prefer the Shared Binary ZIP and extract it to a permanent
              directory, e.g. <code>C:\Tools\ffmpeg</code>.
            </li>
            <li>
              Find the directory containing ffmpeg.exe: typically{" "}
              <code>bin</code> for Shared, or the extraction root for Static.
            </li>
            <li>
              Add that directory to your Windows user PATH and reopen the
              terminal.
            </li>
          </ol>
          <pre>
            <HighlightedCode
              language="powershell"
              code={
                "ffmpeg -version\nffprobe -hide_banner input.mp4\nffmpeg -i input.mp4 output.mkv"
              }
            />
          </pre>
          <p>
            These commands verify installation, inspect a media file and
            transcode it. Keep matching DLLs next to Shared executables. You can
            also run the tools directly from their directory without changing
            PATH. See{" "}
            {doc(
              "guide",
              "installation-and-first-commands",
              "安装与基本命令",
              "installation and first commands",
            )}
            .
          </p>
        </>
      ),
    },
    {
      q: t(
        lang,
        "How do I use FFmpeg in my application?",
        "如何在自己的程序中使用 FFmpeg？",
      ),
      answer: zh ? (
        <>
          <p>
            使用共享库二进制包中的头文件和导入库即可集成
            FFmpeg。选择与目标程序架构一致的构建，将解压目录设为{" "}
            <code>FFMPEG_ROOT</code>，使用随包提供的 CMake 模块：
          </p>
          <pre>
            <HighlightedCode
              language="cmake"
              code={
                'list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")\nfind_package(FFmpeg MODULE REQUIRED)\ntarget_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)'
              }
            />
          </pre>
          <p>
            其中 myapp 是已有的 CMake 目标。配置时传入{" "}
            <code>-DFFMPEG_ROOT=C:/Tools/ffmpeg</code>；运行时确保匹配的 DLL
            可加载。如果不使用 CMake，则手动设置 include、lib 和运行时 DLL
            路径。参见
            {doc(
              "integration",
              "minimal-version",
              "最小版本",
              "完整 CMake 示例",
            )}{" "}
            及
            {doc(
              "integration",
              "with-dll-deployment-windows-shared-builds",
              "带-dll-自动部署windows-共享构建",
              "DLL 自动部署",
            )}
            。
          </p>
        </>
      ) : (
        <>
          <p>
            Link your application against the import libraries and headers from
            Shared Binary. Choose the matching target architecture and set{" "}
            <code>FFMPEG_ROOT</code> to the extracted directory and use its
            supplied CMake module:
          </p>
          <pre>
            <HighlightedCode
              language="cmake"
              code={
                'list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")\nfind_package(FFmpeg MODULE REQUIRED)\ntarget_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)'
              }
            />
          </pre>
          <p>
            Here myapp is an existing CMake target. Configure with{" "}
            <code>-DFFMPEG_ROOT=C:/Tools/ffmpeg</code> and make the matching
            DLLs available at runtime. Without CMake, configure include, lib and
            runtime DLL paths manually. See the{" "}
            {doc(
              "integration",
              "minimal-version",
              "最小版本",
              "complete CMake example",
            )}{" "}
            and{" "}
            {doc(
              "integration",
              "with-dll-deployment-windows-shared-builds",
              "带-dll-自动部署windows-共享构建",
              "automatic DLL deployment",
            )}
            .
          </p>
        </>
      ),
    },
    {
      q: t(lang, "How do I use debug libraries?", "如何使用调试库？"),
      answer: zh ? (
        <>
          <p>
            将调试库与对应二进制包解压至同一目录即可使用。普通运行及 Release
            开发不需要额外下载调试库。
          </p>
          <ol>
            <li>下载同一发布批次、架构、链接方式和许可证的二进制与调试库。</li>
            <li>
              将两个 ZIP
              解压至同一目录，保留原有目录结构。若该版本提供的是开发版，可直接使用该完整包。
            </li>
            <li>
              调试构建使用 <code>debug/lib</code> 的导入库及{" "}
              <code>debug/bin</code> 的 DLL；Release DLL 对应的 PDB 位于{" "}
              <code>bin</code>。在 Visual Studio
              中检查符号是否与已加载模块匹配。
            </li>
          </ol>
          <p>
            不要混用其他构建的 PDB 或 Debug/Release DLL。详见
            {doc(
              "packages",
              "debug-shared-only-requires-binary",
              "调试库仅共享库依赖二进制",
              "调试库内容",
            )}{" "}
            及
            {doc(
              "integration",
              "debug-builds-and-symbols",
              "调试构建与符号",
              "调试构建与符号",
            )}
            。
          </p>
        </>
      ) : (
        <>
          <p>
            Extract Debug over the matching Binary to use debug libraries and
            symbols. Normal execution and Release development do not require
            Debug.
          </p>
          <ol>
            <li>
              Download Binary and Debug from the same release batch,
              architecture, linkage and license.
            </li>
            <li>
              Extract both ZIPs into the same directory, retaining their
              directory structure. If the release offers Develop instead, use
              that complete archive.
            </li>
            <li>
              Use import libraries under <code>debug/lib</code> and DLLs under{" "}
              <code>debug/bin</code> for Debug builds. Release DLL PDBs are
              under <code>bin</code>. In Visual Studio, verify symbols match
              loaded modules.
            </li>
          </ol>
          <p>
            Do not mix PDBs or Debug/Release DLLs from unrelated builds. See{" "}
            {doc(
              "packages",
              "debug-shared-only-requires-binary",
              "调试库仅共享库依赖二进制",
              "debug archive contents",
            )}{" "}
            and{" "}
            {doc(
              "integration",
              "debug-builds-and-symbols",
              "调试构建与符号",
              "debug builds and symbols",
            )}
            .
          </p>
        </>
      ),
    },
    {
      q: t(
        lang,
        "How do I verify a downloaded file?",
        "如何验证下载文件的完整性？",
      ),
      answer: zh ? (
        <>
          <p>
            比较下载文件的 SHA-256
            与网页记录即可验证完整性。打开下载项旁的信息按钮获取摘要，再使用
            PowerShell 计算原始 ZIP 的哈希：
          </p>
          <pre>
            <HighlightedCode
              language="powershell"
              code={
                'Get-FileHash -Algorithm SHA256 -LiteralPath ".\\ffmpeg.zip"'
              }
            />
          </pre>
          <p>
            将示例文件名替换为实际 ZIP 名称，逐字符比较输出的 Hash
            与网页记录（大小写不影响比较）。不一致时不要使用该文件，重新下载并核验。SHA-256
            用于验证文件是否与记录一致，不等同于数字签名。参见
            {doc(
              "guide",
              "verifying-downloads",
              "下载完整性校验",
              "下载完整性校验",
            )}
            。
          </p>
        </>
      ) : (
        <>
          <p>
            Compare the downloaded ZIP's SHA-256 with the catalog digest. Open
            the information button to find the recorded hash, then calculate it
            in PowerShell before extracting:
          </p>
          <pre>
            <HighlightedCode
              language="powershell"
              code={
                'Get-FileHash -Algorithm SHA256 -LiteralPath ".\\ffmpeg.zip"'
              }
            />
          </pre>
          <p>
            Replace the example filename with the actual ZIP name. Compare the
            Hash value with the catalog (case-insensitive). If they differ, do
            not use the file; download it again and verify. SHA-256 checks
            consistency with the recorded file, not a digital signature. See{" "}
            {doc(
              "guide",
              "verifying-downloads",
              "下载完整性校验",
              "verifying downloads",
            )}
            .
          </p>
        </>
      ),
    },
  ];
  return (
    <section className="home-faq" id="faq" aria-labelledby="faq-title">
      <h2 id="faq-title">
        {t(lang, "Frequently asked questions", "常见问题")}
      </h2>
      {questions.map(({ q, answer }) => (
        <details key={q} className="faq-item">
          <summary>
            {q}
            <ChevronDown size={16} aria-hidden="true" />
          </summary>
          <div className="faq-answer">{answer}</div>
        </details>
      ))}
      <div className="faq-footer">
        <Link to={localized(lang, "/guide/")}>
          {t(lang, "Read the documentation", "查看文档")}
          <ArrowUpRight size={14} aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}
