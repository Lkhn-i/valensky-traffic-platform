import { Link, useParams } from "react-router-dom";
import { useApp } from "../app/context";
import { AccessDeniedPanel, AccessPill, Breadcrumbs, ChalkTitle, EntityCover, MaterialCard } from "../components/ui";
import {
  getFolderAccess,
  getFolderById,
  getFoldersForTraining,
  getMaterialAccess,
  getMaterialsForParent,
  getTrainingAccess,
  getTrainingById,
  shouldShowLocked,
} from "../domain/helpers";

export function FolderPage() {
  const { trainingId, folderId } = useParams();
  const { state, currentUser } = useApp();
  const training = getTrainingById(state, trainingId);
  const folder = getFolderById(state, folderId);

  if (!training || !folder || folder.trainingId !== training.id) {
    return (
      <AccessDeniedPanel
        title="Папка не найдена"
        result={{ allowed: false, reason: "unpublished", message: "Материал еще не опубликован" }}
      />
    );
  }

  const trainingAccess = getTrainingAccess(state, training, currentUser);
  if (!trainingAccess.allowed) {
    return <AccessDeniedPanel title={training.title} result={trainingAccess} backTo="/trainings" />;
  }

  const access = getFolderAccess(folder, currentUser);
  if (!access.allowed) {
    return <AccessDeniedPanel title={folder.title} result={access} backTo={`/trainings/${training.id}`} />;
  }

  const materials = getMaterialsForParent(state, "folder", folder.id).filter((material) => {
    const materialAccess = getMaterialAccess(material, currentUser);
    return materialAccess.allowed || shouldShowLocked(material);
  });
  const childFolders = getFoldersForTraining(state, training.id, folder.id).filter((childFolder) => {
    const childAccess = getFolderAccess(childFolder, currentUser);
    return childAccess.allowed || shouldShowLocked(childFolder);
  });

  return (
    <section className="board-section">
      <Breadcrumbs
        items={[
          { label: "Тренинги", to: "/trainings" },
          { label: training.title, to: `/trainings/${training.id}` },
          { label: folder.title },
        ]}
      />
      <div className="folder-open chalk-panel">
        <div>
          <ChalkTitle eyebrow="полезная папка" title={folder.title} text={folder.description} />
          <div className="action-row">
            <Link className="chalk-button ghost" to={`/trainings/${training.id}`}>
              Вернуться к тренингу
            </Link>
            {folder.externalUrl ? (
              <a className="chalk-button" href={folder.externalUrl} target="_blank" rel="noreferrer">
                Открыть внешний ресурс
              </a>
            ) : null}
          </div>
        </div>
        <EntityCover entity={folder} />
      </div>

      {childFolders.length ? (
        <>
          <div className="subsection-head">
            <h2>Вложенные папки</h2>
            <p>Дополнительные материалы и блоки внутри текущей папки.</p>
          </div>
          <div className="folder-grid">
            {childFolders.map((childFolder) => {
              const childAccess = getFolderAccess(childFolder, currentUser);
              const content = (
                <>
                  <EntityCover entity={childFolder} />
                  <span className="chalk-eyebrow">{childFolder.kind === "external" ? "внешний ресурс" : "папка"}</span>
                  <h3>{childFolder.title}</h3>
                  <p>{childFolder.description}</p>
                  <AccessPill result={childAccess} />
                </>
              );
              if (!childAccess.allowed) {
                return (
                  <article className="chalk-card locked-card" key={childFolder.id}>
                    {content}
                  </article>
                );
              }
              if (childFolder.kind === "external" && childFolder.externalUrl) {
                return (
                  <a className="chalk-card folder-card" href={childFolder.externalUrl} target="_blank" rel="noreferrer" key={childFolder.id}>
                    {content}
                  </a>
                );
              }
              return (
                <Link className="chalk-card folder-card" to={`/trainings/${training.id}/folders/${childFolder.id}`} key={childFolder.id}>
                  {content}
                </Link>
              );
            })}
          </div>
        </>
      ) : null}

      <div className="material-grid">
        {materials.map((material) => {
          const materialAccess = getMaterialAccess(material, currentUser);
          return <MaterialCard material={material} accessResult={materialAccess} key={material.id} />;
        })}
      </div>
    </section>
  );
}
