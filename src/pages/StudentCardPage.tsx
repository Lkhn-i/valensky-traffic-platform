import { Link, useParams } from "react-router-dom";
import { useApp } from "../app/context";
import { AccessDeniedPanel, ChalkTitle } from "../components/ui";
import {
  formatHomeworkStatus,
  getLessonById,
  getModuleById,
  getTrainingById,
  getUserById,
  readableDate,
} from "../domain/helpers";

export function StudentCardPage() {
  const { studentId } = useParams();
  const { state, currentUser } = useApp();

  if (!currentUser || (currentUser.role !== "manager" && currentUser.role !== "admin")) {
    return (
      <AccessDeniedPanel
        title="Карточка ученика"
        result={{ allowed: false, reason: "login", message: currentUser ? "Недоступно для текущей роли" : "Нужно войти" }}
      />
    );
  }

  const student = getUserById(state, studentId);
  if (!student || student.role !== "student") {
    return (
      <AccessDeniedPanel
        title="Карточка ученика"
        result={{ allowed: false, reason: "unpublished", message: "Ученик не найден" }}
        backTo="/manager/homeworks"
      />
    );
  }

  const tariff = state.tariffs.find((item) => item.id === student.tariffId);
  const answers = [...state.homeworkAnswers]
    .filter((answer) => answer.studentId === student.id)
    .sort((left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt));
  const stats = {
    всего: answers.length,
    "на проверке": answers.filter((answer) => answer.status === "submitted" || answer.status === "in_review").length,
    принято: answers.filter((answer) => answer.status === "accepted").length,
    доработка: answers.filter((answer) => answer.status === "revision").length,
  };

  return (
    <section className="board-section">
      <ChalkTitle
        eyebrow={tariff?.title || "без тарифа"}
        title={student.name}
        text="Карточка ученика для проверки домашек, статуса доступа и истории работ."
      />

      <div className="student-card-grid">
        <section className="chalk-panel">
          <h2>Профиль</h2>
          <div className="review-meta student-meta">
            <span>{student.email}</span>
            <span>{tariff?.priceLabel || "тариф не выбран"}</span>
            <span>{student.expiresAt ? `доступ до ${readableDate(student.expiresAt)}` : "доступ без даты окончания"}</span>
          </div>
          <p>{student.bio || "Описание ученика пока не заполнено."}</p>
          <div className="mini-list">
            {student.trainingGrantIds.length ? (
              student.trainingGrantIds.map((trainingId) => <span key={trainingId}>{trainingId}</span>)
            ) : (
              <span>доступ по тарифу</span>
            )}
          </div>
        </section>

        <section className="chalk-panel">
          <h2>Домашки</h2>
          <div className="student-stat-grid">
            {Object.entries(stats).map(([label, value]) => (
              <div className="chalk-card compact" key={label}>
                <strong>{value}</strong>
                <span>{label}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="subsection-head">
        <h2>История работ</h2>
      </div>

      <div className="homework-queue">
        {answers.map((answer) => {
          const lesson = getLessonById(state, answer.lessonId);
          const module = lesson ? getModuleById(state, lesson.moduleId) : undefined;
          const training = module ? getTrainingById(state, module.trainingId) : undefined;

          return (
            <article className="chalk-panel review-card" key={answer.id}>
              <div className="review-head">
                <div>
                  <span className="chalk-eyebrow">{training?.title || "тренинг не найден"}</span>
                  <h2>{lesson?.title || "Урок не найден"}</h2>
                </div>
                <span className={`status-pill ${answer.status === "accepted" ? "ok" : "locked"}`}>
                  {formatHomeworkStatus(answer.status)}
                </span>
              </div>
              <div className="review-meta">
                <span>{module?.title}</span>
                <span>{readableDate(answer.submittedAt)}</span>
                <span>обновлено {readableDate(answer.updatedAt)}</span>
              </div>
              <p>{answer.text}</p>
              {answer.reviewerComment ? <p>Комментарий: {answer.reviewerComment}</p> : null}
              <div className="action-row">
                {training && module && lesson ? (
                  <Link className="chalk-button ghost" to={`/trainings/${training.id}/modules/${module.id}/lessons/${lesson.id}`}>
                    Открыть урок
                  </Link>
                ) : null}
                <Link className="chalk-button" to="/manager/homeworks">
                  Вернуться к проверке
                </Link>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
