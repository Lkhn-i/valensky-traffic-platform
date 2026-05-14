import { Link, useParams } from "react-router-dom";
import { useApp } from "../app/context";
import {
  AccessDeniedPanel,
  AccessPill,
  Breadcrumbs,
  ChalkTitle,
  EntityCover,
} from "../components/ui";
import {
  formatDuration,
  getLessonAccess,
  getLessonsForModule,
  getModuleAccess,
  getModuleById,
  getProgressForLesson,
  getTrainingAccess,
  getTrainingById,
  progressRatio,
} from "../domain/helpers";

export function ModulePage() {
  const { trainingId, moduleId } = useParams();
  const { state, currentUser } = useApp();
  const training = getTrainingById(state, trainingId);
  const module = getModuleById(state, moduleId);

  if (!training || !module || module.trainingId !== training.id) {
    return (
      <AccessDeniedPanel
        title="Модуль не найден"
        result={{ allowed: false, reason: "unpublished", message: "Материал еще не опубликован" }}
      />
    );
  }

  const trainingAccess = getTrainingAccess(state, training, currentUser);
  if (!trainingAccess.allowed) {
    return <AccessDeniedPanel title={training.title} result={trainingAccess} backTo="/trainings" />;
  }

  const access = getModuleAccess(state, module, currentUser);
  if (!access.allowed) {
    return <AccessDeniedPanel title={module.title} result={access} backTo={`/trainings/${training.id}`} />;
  }

  const lessons = getLessonsForModule(state, module.id);

  return (
    <section className="board-section">
      <Breadcrumbs
        items={[
          { label: "Тренинги", to: "/trainings" },
          { label: training.title, to: `/trainings/${training.id}` },
          { label: module.title },
        ]}
      />
      <ChalkTitle eyebrow={`Модуль ${module.order}`} title={module.title} text={module.description} />

      <div className="lesson-grid">
        {lessons.map((lesson) => {
          const lessonAccess = getLessonAccess(state, lesson, currentUser);
          const progress = currentUser ? getProgressForLesson(state, lesson.id, currentUser.id) : undefined;
          return (
            <article
              id={`lesson-${lesson.id}`}
              className={lessonAccess.allowed ? "chalk-card lesson-card" : "chalk-card lesson-card locked-card"}
              key={lesson.id}
            >
              <EntityCover entity={lesson} />
              <div className="stats-line">
                <span>Урок {lesson.order}</span>
                <span>{formatDuration(lesson.durationMinutes)}</span>
                <AccessPill result={lessonAccess} />
              </div>
              <h3>{lesson.title}</h3>
              <p>{lesson.summary}</p>
              <div className="progress-track" aria-label={`Прогресс ${progressRatio(progress)}%`}>
                <span style={{ width: `${progressRatio(progress)}%` }} />
              </div>
              {lessonAccess.allowed ? (
                <Link className="chalk-button ghost" to={`/trainings/${training.id}/modules/${module.id}/lessons/${lesson.id}`}>
                  Смотреть урок
                </Link>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
