import hljs from "highlight.js/lib/core";
import powershell from "highlight.js/lib/languages/powershell";
import cmake from "highlight.js/lib/languages/cmake";

hljs.registerLanguage("powershell", powershell);
hljs.registerLanguage("cmake", cmake);

export function HighlightedCode({
  code,
  language,
}: {
  code: string;
  language: string;
}) {
  if (!hljs.getLanguage(language)) return <code>{code}</code>;
  // highlight.js escapes source text before emitting its token spans.
  const html = hljs.highlight(code, { language, ignoreIllegals: true }).value;
  return (
    <code
      className={"hljs language-" + language}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
