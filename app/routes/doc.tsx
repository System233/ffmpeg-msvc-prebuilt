import { HighlightedCode } from "../components/HighlightedCode";
import { readFileSync } from "node:fs";
import { useLoaderData, useParams, Link } from "react-router";
import type {
  LoaderFunctionArgs,
  ShouldRevalidateFunctionArgs,
} from "react-router";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { language, t } from "../lib/i18n";
import { localized } from "../domain/catalog";
export function loader({ request, params }: LoaderFunctionArgs) {
  const doc =
    new URL(request.url).pathname.split("/").filter(Boolean).at(-1) ?? "";
  if (
    ![
      "guide",
      "integration",
      "packages",
      "licenses",
      "reference",
      "self-build",
      "history",
    ].includes(doc)
  )
    throw new Response("Not found", { status: 404 });
  const lang = language(params.lang);
  const markdown = readFileSync(
    "docs/" + lang + "/" + doc + ".md",
    "utf8",
  ).replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "");
  return { markdown, doc, lang };
}
export function shouldRevalidate({
  currentParams,
  nextParams,
  defaultShouldRevalidate,
}: ShouldRevalidateFunctionArgs) {
  return currentParams.lang !== nextParams.lang || defaultShouldRevalidate;
}
function docLinks(lang: ReturnType<typeof language>) {
  return [
    ["guide", t(lang, "Guide", "使用指南")],
    ["integration", t(lang, "Integration", "开发集成")],
    ["packages", t(lang, "Build artifacts", "构建产物")],
    ["licenses", t(lang, "Licenses and redistribution", "许可证与再分发")],
    ["self-build", t(lang, "Build from source", "自行构建")],
    ["reference", t(lang, "Reference", "参考")],
    ["history", t(lang, "Update history", "更新历史")],
  ];
}
export const meta = ({
  data,
}: {
  data?: Awaited<ReturnType<typeof loader>>;
}) => [
  {
    title:
      ((data && docLinks(data.lang).find(([path]) => path === data.doc)?.[1]) ||
        "Docs") + " | FFmpeg MSVC Prebuilt",
  },
];
function slug(text: string) {
  return (
    text
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s-]/gu, "")
      .trim()
      .replace(/\s+/g, "-") || "section"
  );
}
function headings(markdown: string) {
  const seen = new Map<string, number>();
  let fence = false;
  return markdown.split(/\r?\n/).flatMap((line, i) => {
    if (/^\s*(?:```|~~~)/.test(line)) {
      fence = !fence;
      return [];
    }
    const m = !fence && /^(#{2,3})\s+(.+?)\s*#*\s*$/.exec(line);
    if (!m) return [];
    const base = slug(m[2]);
    const n = seen.get(base) ?? 0;
    seen.set(base, n + 1);
    return [
      {
        line: i + 1,
        id: n ? base + "-" + n : base,
        text: m[2].replace(/[*`]/g, ""),
        level: m[1].length,
      },
    ];
  });
}
export default function Doc() {
  const { markdown, doc } = useLoaderData<typeof loader>(),
    lang = language(useParams().lang);
  const toc = headings(markdown);
  const links = docLinks(lang);
  return (
    <div className="doc-layout">
      <nav
        className="doc-nav"
        aria-label={t(lang, "Documentation", "文档导航")}
      >
        <h2>{t(lang, "Documentation", "文档")}</h2>
        {links.map(([path, label]) => (
          <Link
            key={path}
            to={localized(lang, "/" + path + "/")}
            className={path === doc ? "active" : undefined}
            aria-current={path === doc ? "page" : undefined}
          >
            {label}
          </Link>
        ))}
      </nav>
      <article className="prose">
        <Markdown
          remarkPlugins={[remarkGfm]}
          components={{
            code: ({ node: _node, className, children, ...props }) => {
              const language = /(?:^|\s)language-([\w+-]+)/.exec(
                className ?? "",
              )?.[1];
              return language && typeof children === "string" ? (
                <HighlightedCode code={children} language={language} />
              ) : (
                <code className={className} {...props}>
                  {children}
                </code>
              );
            },
            h2: ({ node, children }) => (
              <h2
                id={toc.find((x) => x.line === node?.position?.start.line)?.id}
              >
                {children}
              </h2>
            ),
            h3: ({ node, children }) => (
              <h3
                id={toc.find((x) => x.line === node?.position?.start.line)?.id}
              >
                {children}
              </h3>
            ),
          }}
        >
          {markdown}
        </Markdown>
      </article>
      <nav className="doc-toc" aria-label={t(lang, "On this page", "本页目录")}>
        <h2>{t(lang, "On this page", "本页目录")}</h2>
        {toc.map((h) => (
          <a
            key={h.id}
            href={"#" + h.id}
            style={{ paddingLeft: h.level === 3 ? 18 : 8 }}
          >
            {h.text}
          </a>
        ))}
      </nav>
    </div>
  );
}
