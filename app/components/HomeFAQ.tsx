import { Link } from "react-router";
import { ArrowUpRight, ChevronDown } from "lucide-react";
import { localized } from "../i18n/routing";
import { t, type Language } from "../i18n";

export function HomeFAQ({
  lang,
  questions,
}: {
  lang: Language;
  questions: readonly { q: string; html: string }[];
}) {
  return (
    <section className="home-faq" id="faq" aria-labelledby="faq-title">
      <h2 id="faq-title">{t(lang, "homeFAQ.frequentlyAskedQuestions")}</h2>
      {questions.map(({ q, html }) => (
        <details key={q} className="faq-item">
          <summary>
            {q}
            <ChevronDown size={16} aria-hidden="true" />
          </summary>
          <div
            className="faq-answer"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        </details>
      ))}
      <div className="faq-footer">
        <Link to={localized(lang, "/guide/")}>
          {t(lang, "homeFAQ.readTheDocumentation")}
          <ArrowUpRight size={14} aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}
