import { documentPages, isDocumentPage } from "../content/config";
import { loadDocument } from "../content/markdown.server";
import { useLoaderData, useParams, Link } from "react-router";
import type {
  LoaderFunctionArgs,
  ShouldRevalidateFunctionArgs,
} from "react-router";
import { language, t } from "../i18n";
import { localized } from "../i18n/routing";
export function loader({ request, params }: LoaderFunctionArgs) {
  const doc =
    new URL(request.url).pathname.split("/").filter(Boolean).at(-1) ?? "";
  if (!isDocumentPage(doc)) throw new Response("Not found", { status: 404 });
  const lang = language(params.lang);
  return { ...loadDocument(lang, doc), doc, lang };
}
export function shouldRevalidate({
  currentParams,
  nextParams,
  defaultShouldRevalidate,
}: ShouldRevalidateFunctionArgs) {
  return currentParams.lang !== nextParams.lang || defaultShouldRevalidate;
}
function docLinks(lang: ReturnType<typeof language>) {
  return documentPages.map(([path, key]) => [path, t(lang, key)] as const);
}
export const meta = ({
  data,
}: {
  data?: Awaited<ReturnType<typeof loader>>;
}) => [
  {
    title:
      ((data && docLinks(data.lang).find(([path]) => path === data.doc)?.[1]) ||
        t(data?.lang ?? "en", "seo.docsFallback")) + " | FFmpeg MSVC Prebuilt",
  },
];
export default function Doc() {
  const { html, toc, doc } = useLoaderData<typeof loader>(),
    lang = language(useParams().lang);
  const links = docLinks(lang);
  return (
    <div className="doc-layout">
      <nav className="doc-nav" aria-label={t(lang, "doc.navLabel")}>
        <h2>{t(lang, "doc.title")}</h2>
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
      <article className="prose" dangerouslySetInnerHTML={{ __html: html }} />
      <nav className="doc-toc" aria-label={t(lang, "doc.onThisPage")}>
        <h2>{t(lang, "doc.onThisPage")}</h2>
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
