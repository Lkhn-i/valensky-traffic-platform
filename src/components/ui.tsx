import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import {
  legalDocuments,
  paymentRequiredLegalDocumentIds,
  siteRequiredLegalDocumentIds,
  type LegalDocumentId,
} from "../domain/legal";
import type { AccessResult, BaseEntity, Material, Module, TariffId } from "../domain/types";

export function ChalkTitle({
  eyebrow,
  title,
  text,
}: {
  eyebrow?: string;
  title: string;
  text?: string;
}) {
  return (
    <div className="section-title">
      {eyebrow ? <span className="chalk-eyebrow">{eyebrow}</span> : null}
      <h1>{title}</h1>
      {text ? <p>{text}</p> : null}
    </div>
  );
}

export function Breadcrumbs({ items }: { items: Array<{ label: string; to?: string }> }) {
  return (
    <nav className="breadcrumbs" aria-label="Хлебные крошки">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`}>
          {item.to ? <Link to={item.to}>{item.label}</Link> : <strong>{item.label}</strong>}
        </span>
      ))}
    </nav>
  );
}

export function EntityCover({ entity, className = "" }: { entity: Pick<BaseEntity, "coverImage" | "title">; className?: string }) {
  const hasCustomImage = Boolean(entity.coverImage && !entity.coverImage.startsWith("data:image/svg+xml"));

  return (
    <div className={`cover-frame ${className}`}>
      {hasCustomImage ? (
        <img src={entity.coverImage} alt="" />
      ) : (
        <div className="cover-placeholder">
          <span className="cover-placeholder-mark" aria-hidden="true" />
          <span className="cover-placeholder-label">Место для обложки</span>
        </div>
      )}
    </div>
  );
}

export function AccessPill({ result }: { result: AccessResult }) {
  return <span className={result.allowed ? "status-pill ok" : "status-pill locked"}>{result.message}</span>;
}

export function LegalConsent({
  id,
  checked,
  onChange,
  context = "access",
}: {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  context?: "access" | "payment";
}) {
  const intro = context === "payment" ? "Перед оплатой принимаю" : "Для входа принимаю";
  const documents = context === "payment" ? paymentRequiredLegalDocumentIds : siteRequiredLegalDocumentIds;

  return (
    <label className="legal-consent" htmlFor={id}>
      <input id={id} type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>
        {intro} <LegalDocumentLinks documentIds={documents} />.
      </span>
    </label>
  );
}

export function MarketingConsent({
  id,
  checked,
  onChange,
}: {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="legal-consent optional-consent" htmlFor={id}>
      <input id={id} type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>
        Хочу получать полезные материалы и новости курса, принимаю{" "}
        <a href={legalDocuments.marketingConsent.url} target="_blank" rel="noreferrer">
          {legalDocuments.marketingConsent.shortTitle}
        </a>
        . Это необязательно для покупки.
      </span>
    </label>
  );
}

export function LegalDocumentLinks({ documentIds }: { documentIds: readonly LegalDocumentId[] }) {
  return (
    <>
      {documentIds.map((documentId, index) => {
        const document = legalDocuments[documentId];
        const separator = index === 0 ? "" : index === documentIds.length - 1 ? " и " : ", ";
        return (
          <span key={documentId}>
            {separator}
            <a href={document.url} target="_blank" rel="noreferrer">
              {document.shortTitle}
            </a>
          </span>
        );
      })}
    </>
  );
}

export function AccessDeniedPanel({
  title,
  result,
  backTo,
}: {
  title: string;
  result: AccessResult;
  backTo?: string;
}) {
  const isConditionMessage = result.reason === "time" || result.reason === "previous" || result.reason === "previous_time";
  return (
    <section className="chalk-panel access-panel">
      <span className="chalk-eyebrow">Доступ закрыт</span>
      <h1>{title}</h1>
      <p className={isConditionMessage ? "access-condition-text" : undefined}>{result.message}</p>
      <div className="action-row">
        <Link className="chalk-button" to="/#tariffs">
          Посмотреть тарифы
        </Link>
        <a className="chalk-button ghost" href="https://t.me/valenskymanager" target="_blank" rel="noreferrer">
          Написать в поддержку
        </a>
        {backTo ? (
          <Link className="chalk-button ghost" to={backTo}>
            Вернуться к тренингу
          </Link>
        ) : null}
      </div>
    </section>
  );
}

export function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}

export function TariffBadges({ tariffIds }: { tariffIds: TariffId[] }) {
  if (tariffIds.length === 0) {
    return <span className="mini-badge">без ограничений</span>;
  }
  return (
    <span className="badge-row">
      {tariffIds.map((id) => (
        <span className="mini-badge" key={id}>
          {id === "zero"
            ? "нулевой урок"
            : id === "workshop"
              ? "воркшоп"
              : id === "basic"
                ? "базовый"
                : id === "mentor"
                  ? "с ментором"
                  : "VIP"}
        </span>
      ))}
    </span>
  );
}

function formatMaterialSize(size?: number) {
  if (!size) {
    return "";
  }
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} КБ`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} МБ`;
}

export function LinkifiedText({ text }: { text: string }) {
  const nodes: ReactNode[] = [];
  const urlPattern = /(https?:\/\/[^\s<]+|www\.[^\s<]+)/gi;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = urlPattern.exec(text)) !== null) {
    const rawUrl = match[0];
    const punctuation = rawUrl.match(/[.,!?;:)]+$/)?.[0] || "";
    const cleanUrl = punctuation ? rawUrl.slice(0, -punctuation.length) : rawUrl;
    const href = cleanUrl.startsWith("www.") ? `https://${cleanUrl}` : cleanUrl;

    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    nodes.push(
      <a className="inline-link" href={href} target="_blank" rel="noreferrer" key={`${href}-${match.index}`}>
        {cleanUrl}
      </a>,
    );
    if (punctuation) {
      nodes.push(punctuation);
    }
    lastIndex = match.index + rawUrl.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return <>{nodes}</>;
}

export function MaterialCard({
  material,
  accessResult,
}: {
  material: Material;
  accessResult?: AccessResult;
}) {
  const locked = accessResult ? !accessResult.allowed : false;
  const isFile = material.materialType === "file" || Boolean(material.fileName);
  const fileSize = formatMaterialSize(material.fileSize);
  return (
    <article id={`material-${material.id}`} className={locked ? "chalk-card material-card locked-card" : "chalk-card material-card"}>
      <EntityCover entity={material} />
      <div>
        <span className="chalk-eyebrow">{material.metaLabel || material.materialType}</span>
        <h3>{material.title}</h3>
        {locked ? <AccessPill result={accessResult as AccessResult} /> : <p><LinkifiedText text={material.description} /></p>}
        {!locked && material.body ? <small><LinkifiedText text={material.body} /></small> : null}
        {!locked && material.fileName ? (
          <small>
            Файл: {material.fileName}
            {fileSize ? ` · ${fileSize}` : ""}
          </small>
        ) : null}
        {!locked && material.url ? (
          <a className="inline-link material-download-link" href={material.url} target="_blank" rel="noreferrer">
            {isFile ? "Скачать файл" : "Открыть материал"}
          </a>
        ) : null}
      </div>
    </article>
  );
}

export function ModuleStats({ module, count }: { module: Module; count: number }) {
  return (
    <div className="stats-line">
      <span>Модуль {module.order}</span>
      <span>{count} уроков</span>
      <TariffBadges tariffIds={module.accessPolicy.tariffIds} />
    </div>
  );
}
