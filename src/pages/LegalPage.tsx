import { Link, useParams } from "react-router-dom";
import { Breadcrumbs, ChalkTitle } from "../components/ui";
import { legalDocuments, type LegalDocumentId } from "../domain/legal";

export function LegalPage() {
  const { documentId } = useParams();
  const aliases: Record<string, LegalDocumentId> = {
    consent: "personalDataConsent",
    personal: "personalDataConsent",
    marketing: "marketingConsent",
  };
  const resolvedDocumentId = aliases[documentId || ""] || ((documentId || "offer") as LegalDocumentId);
  const document = legalDocuments[resolvedDocumentId] || legalDocuments.offer;

  return (
    <section className="board-section legal-page">
      <Breadcrumbs items={[{ label: "Главная", to: "/" }, { label: document.title }]} />
      <ChalkTitle
        eyebrow="юридический раздел"
        title={document.title}
        text="Документ хранится во внешнем Google Docs и открывается в новой вкладке."
      />
      <div className="chalk-panel">
        <h2>Внешний документ</h2>
        <p>При клике откроется актуальная версия документа. Ссылка также доступна в футере сайта и в нужных формах согласия.</p>
        <a className="chalk-button" href={document.url} target="_blank" rel="noreferrer">
          Открыть Google Документ
        </a>
        <Link className="chalk-button ghost" to="/">
          Вернуться на главную
        </Link>
      </div>
    </section>
  );
}
