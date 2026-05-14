import { Link, useParams } from "react-router-dom";
import { useApp } from "../app/context";
import {
  AccessDeniedPanel,
  AccessPill,
  Breadcrumbs,
  ChalkTitle,
  EntityCover,
  ModuleStats,
} from "../components/ui";
import {
  getFolderAccess,
  getFoldersForTraining,
  getLessonsForModule,
  getModuleAccess,
  getModulesForTraining,
  getTrainingAccess,
  getTrainingById,
  moduleProgressRatio,
  shouldShowLocked,
} from "../domain/helpers";

export function TrainingPage() {
  const { trainingId } = useParams();
  const { state, currentUser } = useApp();
  const training = getTrainingById(state, trainingId);

  if (!training) {
    return (
      <AccessDeniedPanel
        title="Тренинг не найден"
        result={{ allowed: false, reason: "unpublished", message: "Материал еще не опубликован" }}
      />
    );
  }

  const access = getTrainingAccess(state, training, currentUser);
  if (!access.allowed) {
    return <AccessDeniedPanel title={training.title} result={access} backTo="/trainings" />;
  }

  const tariff = state.tariffs.find((item) => item.id === currentUser?.tariffId);
  const folders = getFoldersForTraining(state, training.id).filter((folder) => {
    const folderAccess = getFolderAccess(folder, currentUser);
    return folderAccess.allowed || shouldShowLocked(folder);
  });
  const modules = getModulesForTraining(state, training.id).filter((module) => {
    const moduleAccess = getModuleAccess(state, module, currentUser);
    return moduleAccess.allowed || shouldShowLocked(module);
  });

  return (
    <section className="board-section">
      <Breadcrumbs items={[{ label: "Тренинги", to: "/trainings" }, { label: training.title }]} />
      <ChalkTitle eyebrow={training.tagline} title={training.title} text={training.description} />

      <div className="training-hero chalk-panel">
        <div>
          <span className="chalk-eyebrow">Ваш тариф: {tariff?.title || "не выбран"}</span>
          <h2>{training.subtitle}</h2>
          <p>{training.tagline}</p>
        </div>
        <EntityCover entity={training} className="wide-cover" />
      </div>

      <div className="subsection-head">
        <h2>Полезные блоки</h2>
        <p>Папки и внешние ресурсы выводятся из данных платформы и учитывают тариф.</p>
      </div>
      <div className="folder-grid">
        {folders.map((folder) => {
          const folderAccess = getFolderAccess(folder, currentUser);
          const content = (
            <>
              <EntityCover entity={folder} />
              <span className="chalk-eyebrow">{folder.kind === "external" ? "внешний ресурс" : "папка"}</span>
              <h3>{folder.title}</h3>
              <p>{folder.description}</p>
              <AccessPill result={folderAccess} />
            </>
          );
          if (!folderAccess.allowed) {
            return (
              <article id={`folder-${folder.id}`} className="chalk-card locked-card" key={folder.id}>
                {content}
              </article>
            );
          }
          if (folder.kind === "external" && folder.externalUrl) {
            return (
              <a
                id={`folder-${folder.id}`}
                className="chalk-card folder-card"
                href={folder.externalUrl}
                target="_blank"
                rel="noreferrer"
                key={folder.id}
              >
                {content}
              </a>
            );
          }
          return (
            <Link
              id={`folder-${folder.id}`}
              className="chalk-card folder-card"
              to={`/trainings/${training.id}/folders/${folder.id}`}
              key={folder.id}
            >
              {content}
            </Link>
          );
        })}
      </div>

      <div className="subsection-head">
        <h2>Модули обучения</h2>
        <p>Порядок, статусы и доступы задаются в админке.</p>
      </div>
      <div className="module-grid">
        {modules.map((module) => {
          const moduleAccess = getModuleAccess(state, module, currentUser);
          const lessonCount = getLessonsForModule(state, module.id).filter((lesson) => lesson.status === "published").length;
          const moduleProgress = currentUser ? moduleProgressRatio(state, module.id, currentUser.id) : 0;
          return (
            <article
              id={`module-${module.id}`}
              className={moduleAccess.allowed ? "chalk-card module-card" : "chalk-card module-card locked-card"}
              key={module.id}
            >
              <EntityCover entity={module} />
              <ModuleStats module={module} count={lessonCount} />
              <h3>{module.title}</h3>
              <p>{module.description}</p>
              <div className="progress-track module-progress-track" aria-label={`Прогресс модуля ${moduleProgress}%`}>
                <span style={{ width: `${moduleProgress}%` }} />
              </div>
              {moduleAccess.allowed ? (
                <Link className="chalk-button ghost" to={`/trainings/${training.id}/modules/${module.id}`}>
                  Смотреть уроки
                </Link>
              ) : (
                <AccessPill result={moduleAccess} />
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
