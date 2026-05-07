import { Link } from "react-router-dom";
import { useApp } from "../app/context";
import { AccessDeniedPanel, AccessPill, ChalkTitle, EntityCover, EmptyState } from "../components/ui";
import { getPublishedLessonCount, getTrainingAccess, getUserTrainings } from "../domain/helpers";

export function TrainingsPage() {
  const { state, currentUser } = useApp();

  if (!currentUser) {
    return (
      <AccessDeniedPanel
        title="Список тренингов"
        result={{ allowed: false, reason: "login", message: "Нужно войти" }}
      />
    );
  }

  const trainings = getUserTrainings(state, currentUser);

  return (
    <section className="board-section">
      <ChalkTitle
        eyebrow={currentUser.name}
        title="Список тренингов"
        text="Здесь видны только те тренинги и материалы, которые входят в текущий доступ."
      />

      <div className="chalk-panel">
        <h2>Доступные тренинги</h2>
        {trainings.length === 0 ? (
          <EmptyState title="Пока ничего не открыто" text="Напишите в поддержку, чтобы проверить доступ." />
        ) : (
          <div className="training-list">
            {trainings.map((training) => {
              const access = getTrainingAccess(state, training, currentUser);
              const content = (
                <>
                  <EntityCover entity={training} />
                  <span>
                    <strong>{training.title}</strong>
                    <small>{training.subtitle}</small>
                  </span>
                  <b>{getPublishedLessonCount(state, training.id)} уроков</b>
                  <AccessPill result={access} />
                </>
              );
              return access.allowed ? (
                <Link className="training-row" to={`/trainings/${training.id}`} key={training.id}>
                  {content}
                </Link>
              ) : (
                <article className="training-row locked-card" key={training.id}>
                  {content}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
