import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
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
import type { HomeworkStatus } from "../domain/types";

const statuses: HomeworkStatus[] = ["submitted", "in_review", "accepted", "revision"];

export function ManagerHomeworksPage() {
  const { state, currentUser, reviewHomework } = useApp();
  const [commentDrafts, setCommentDrafts] = useState<Record<string, string>>({});
  const syncedCommentsRef = useRef<Record<string, string>>({});

  useEffect(() => {
    setCommentDrafts((current) => {
      const nextDrafts: Record<string, string> = {};
      const nextSyncedComments: Record<string, string> = {};
      let hasChanges = Object.keys(current).length !== state.homeworkAnswers.length;

      for (const answer of state.homeworkAnswers) {
        const syncedComment = syncedCommentsRef.current[answer.id];
        const nextComment =
          current[answer.id] === undefined || syncedComment !== answer.reviewerComment
            ? answer.reviewerComment
            : current[answer.id];

        nextDrafts[answer.id] = nextComment;
        nextSyncedComments[answer.id] = answer.reviewerComment;

        if (nextComment !== current[answer.id]) {
          hasChanges = true;
        }
      }

      syncedCommentsRef.current = nextSyncedComments;
      return hasChanges ? nextDrafts : current;
    });
  }, [state.homeworkAnswers]);

  if (!currentUser || (currentUser.role !== "manager" && currentUser.role !== "admin")) {
    return (
      <AccessDeniedPanel
        title="Проверка домашних"
        result={{ allowed: false, reason: "login", message: "Нужно войти" }}
      />
    );
  }

  const answers = [...state.homeworkAnswers].sort(
    (left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt),
  );

  return (
    <section className="board-section">
      <ChalkTitle
        eyebrow="лента ответов"
        title="Проверка домашних заданий"
        text="Работы учеников сгруппированы с привязкой к тарифу, тренингу, модулю и уроку."
      />

      <div className="homework-queue">
        {answers.map((answer) => {
          const lesson = getLessonById(state, answer.lessonId);
          const module = lesson ? getModuleById(state, lesson.moduleId) : undefined;
          const training = module ? getTrainingById(state, module.trainingId) : undefined;
          const student = getUserById(state, answer.studentId);
          const tariff = state.tariffs.find((item) => item.id === student?.tariffId);

          return (
            <article className="chalk-panel review-card" key={answer.id}>
              <div className="review-head">
                <div>
                  <span className="chalk-eyebrow">{tariff?.title || "без тарифа"}</span>
                  <h2>{student?.name || "Ученик"}</h2>
                </div>
                <span className={`status-pill ${answer.status === "accepted" ? "ok" : "locked"}`}>
                  {formatHomeworkStatus(answer.status)}
                </span>
              </div>

              <div className="review-meta">
                <span>{training?.title}</span>
                <span>{module?.title}</span>
                <span>{lesson?.title}</span>
                <span>{readableDate(answer.submittedAt)}</span>
              </div>

              <p>{answer.text}</p>

              {answer.attachments.length ? (
                <div className="mini-list">
                  {answer.attachments.map((file) => (
                    <span key={file.name}>
                      {file.url ? (
                        <a className="inline-link" href={file.url} target="_blank" rel="noreferrer">
                          {file.name}
                        </a>
                      ) : (
                        file.name
                      )}
                    </span>
                  ))}
                </div>
              ) : null}

              <label>
                Комментарий проверки
                <textarea
                  rows={3}
                  value={commentDrafts[answer.id] ?? answer.reviewerComment}
                  onChange={(event) =>
                    setCommentDrafts((current) => ({
                      ...current,
                      [answer.id]: event.target.value,
                    }))
                  }
                  onBlur={() =>
                    reviewHomework(
                      answer.id,
                      answer.status,
                      commentDrafts[answer.id] ?? answer.reviewerComment,
                    )
                  }
                />
              </label>

              <div className="action-row">
                {statuses.map((status) => (
                  <button
                    className="chalk-button ghost"
                    type="button"
                    key={status}
                    onClick={() =>
                      reviewHomework(
                        answer.id,
                        status,
                        commentDrafts[answer.id] ?? answer.reviewerComment,
                      )
                    }
                  >
                    {formatHomeworkStatus(status)}
                  </button>
                ))}
                {training && module && lesson ? (
                  <Link className="chalk-button" to={`/trainings/${training.id}/modules/${module.id}/lessons/${lesson.id}`}>
                    Открыть урок
                  </Link>
                ) : null}
                {student ? (
                  <Link className="chalk-button ghost" to={`/manager/students/${student.id}`}>
                    Карточка ученика
                  </Link>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
