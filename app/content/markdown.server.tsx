import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { base } from "../../scripts/site-config";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { HighlightedCode } from "../components/HighlightedCode";
import { localized } from "../i18n/routing";
import type { Language } from "../i18n";
function LocalizedMarkdown({
  lang,
  markdown,
  components,
}: {
  lang: Language;
  markdown: string;
  components?: Components;
}) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ node: _node, href, children, ...props }) =>
          href?.startsWith("/") && !href.startsWith("//") ? (
            <a href={base + localized(lang, href).slice(1)} {...props}>
              {children}
            </a>
          ) : (
            <a href={href} {...props}>
              {children}
            </a>
          ),
        code: ({ node: _node, className, children, ...props }) => {
          const language = /(?:^|\s)language-([\w+-]+)/.exec(
            className ?? "",
          )?.[1];
          return language && typeof children === "string" ? (
            <HighlightedCode language={language} code={children.trimEnd()} />
          ) : (
            <code className={className} {...props}>
              {children}
            </code>
          );
        },
        ...components,
      }}
    >
      {markdown}
    </Markdown>
  );
}

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

function readContent(lang: Language, name: string) {
  return readFileSync("docs/" + lang + "/" + name + ".md", "utf8").replace(
    /^---\r?\n[\s\S]*?\r?\n---\r?\n/,
    "",
  );
}
// Markdown is trusted repository content. React Markdown escapes raw HTML and
// filters unsafe URLs; HighlightedCode escapes source before highlighting.
export function loadDocument(lang: Language, name: string) {
  const markdown = readContent(lang, name);
  const toc = headings(markdown);
  const id = (line?: number) => toc.find((x) => x.line === line)?.id;
  const html = renderToStaticMarkup(
    <LocalizedMarkdown
      lang={lang}
      markdown={markdown}
      components={{
        h2: ({ node, children }) => (
          <h2 id={id(node?.position?.start.line)}>{children}</h2>
        ),
        h3: ({ node, children }) => (
          <h3 id={id(node?.position?.start.line)}>{children}</h3>
        ),
      }}
    />,
  );
  return { html, toc };
}
export function loadFAQ(lang: Language) {
  const markdown = readContent(lang, "faq");
  return markdown
    .trim()
    .split(/^## /m)
    .filter(Boolean)
    .map((section) => {
      const newline = section.indexOf("\n");
      if (newline < 0) throw Error("FAQ question is missing an answer");
      const q = section.slice(0, newline).trim();
      const answer = section.slice(newline + 1).trim();
      return {
        q,
        html: renderToStaticMarkup(
          <LocalizedMarkdown lang={lang} markdown={answer} />,
        ),
      };
    });
}
