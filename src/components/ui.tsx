import { Link } from "react-router-dom";
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
  return (
    <div className={`cover-frame ${className}`}>
      {entity.coverImage ? <img src={entity.coverImage} alt="" /> : <span>{entity.title}</span>}
    </div>
  );
}

export function AccessPill({ result }: { result: AccessResult }) {
  return <span className={result.allowed ? "status-pill ok" : "status-pill locked"}>{result.message}</span>;
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
  return (
    <section className="chalk-panel access-panel">
      <span className="chalk-eyebrow">Доступ закрыт</span>
      <h1>{title}</h1>
      <p>{result.message}</p>
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
          {id === "workshop" ? "воркшоп" : id === "basic" ? "базовый" : id === "mentor" ? "ментор" : "vip"}
        </span>
      ))}
    </span>
  );
}

export function MaterialCard({
  material,
  accessResult,
}: {
  material: Material;
  accessResult?: AccessResult;
}) {
  const locked = accessResult ? !accessResult.allowed : false;
  return (
    <article className={locked ? "chalk-card material-card locked-card" : "chalk-card material-card"}>
      <EntityCover entity={material} />
      <div>
        <span className="chalk-eyebrow">{material.metaLabel || material.materialType}</span>
        <h3>{material.title}</h3>
        {locked ? <AccessPill result={accessResult as AccessResult} /> : <p>{material.description}</p>}
        {!locked && material.body ? <small>{material.body}</small> : null}
        {!locked && material.url ? (
          <a className="inline-link" href={material.url} target="_blank" rel="noreferrer">
            Открыть материал
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
