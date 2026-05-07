import { ChangeEvent, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApp } from "../app/context";
import {
  AccessDeniedPanel,
  Breadcrumbs,
  ChalkTitle,
  MaterialCard,
} from "../components/ui";
import {
  formatHomeworkStatus,
  getBlocksForLesson,
  getHomeworkForLesson,
  getLessonAccess,
  getLessonById,
  getMaterialAccess,
  getMaterialsForParent,
  getModuleAccess,
  getModuleById,
  getNextLesson,
  getProgressForLesson,
  getTrainingAccess,
  getTrainingById,
  progressRatio,
  shouldShowLocked,
} from "../domain/helpers";
import type { HomeworkAttachment } from "../domain/types";

export function LessonPage() {
  const { trainingId, moduleId, lessonId } = useParams();
  const { state, currentUser, submitHomework, saveProgress, uploadHomeworkFiles } = useApp();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const training = getTrainingById(state, trainingId);
  const module = getModuleById(state, moduleId);
  const lesson = getLessonById(state, lessonId);
  const homework = currentUser && lesson ? getHomeworkForLesson(state, lesson.id, currentUser.id) : undefined;
  const [homeworkText, setHomeworkText] = useState("");
  const [attachments, setAttachments] = useState<HomeworkAttachment[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");

  useEffect(() => {
    setHomeworkText(homework?.text ?? "");
    setAttachments([]);
  }, [homework?.id, homework?.text]);

  if (!training || !module || !lesson || module.trainingId !== training.id || lesson.moduleId !== module.id) {
    return (
      <AccessDeniedPanel
        title="Урок не найден"
        result={{ allowed: false, reason: "unpublished", message: "Материал еще не опубликован" }}
      />
    );
  }

  const trainingAccess = getTrainingAccess(state, training, currentUser);
  if (!trainingAccess.allowed) {
    return <AccessDeniedPanel title={training.title} result={trainingAccess} backTo="/trainings" />;
  }

  const moduleAccess = getModuleAccess(state, module, currentUser);
  if (!moduleAccess.allowed) {
    return <AccessDeniedPanel title={module.title} result={moduleAccess} backTo={`/trainings/${training.id}`} />;
  }

  const access = getLessonAccess(state, lesson, currentUser);
  if (!access.allowed) {
    return <AccessDeniedPanel title={lesson.title} result={access} backTo={`/trainings/${training.id}`} />;
  }

  const blocks = getBlocksForLesson(state, lesson.id);
  const materials = getMaterialsForParent(state, "lesson", lesson.id).filter((material) => {
    const materialAccess = getMaterialAccess(material, currentUser);
    return materialAccess.allowed || shouldShowLocked(material);
  });
  const template = state.homeworkTemplates.find((item) => item.id === lesson.homeworkTemplateId);
  const progress = currentUser ? getProgressForLesson(state, lesson.id, currentUser.id) : undefined;
  const nextLesson = getNextLesson(state, lesson);
  const homeworkAllowed =
    currentUser?.role === "student" &&
    Boolean(template && currentUser.tariffId && template.requiredTariffIds.includes(currentUser.tariffId));

  const handleTimeUpdate = () => {
    if (currentUser?.role !== "student") {
      return;
    }
    const video = videoRef.current;
    if (!video) {
      return;
    }
    saveProgress(lesson.id, {
      watchedSeconds: Math.max(progress?.watchedSeconds || 0, Math.round(video.currentTime)),
      durationSeconds: Math.round(video.duration || lesson.durationMinutes * 60),
      lastPositionSeconds: Math.round(video.currentTime),
      isCompleted: video.currentTime > 0 && video.duration > 0 && video.currentTime / video.duration > 0.9,
    });
  };

  const handleFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    setUploadError("");
    if (!files.length) {
      setAttachments([]);
      return;
    }
    setIsUploading(true);
    try {
      const uploadedFiles = await uploadHomeworkFiles(files);
      setAttachments(uploadedFiles);
    } catch {
      setAttachments([]);
      setUploadError("Не удалось загрузить файлы. Попробуйте еще раз.");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <section className="board-section">
      <Breadcrumbs
        items={[
          { label: "Тренинги", to: "/trainings" },
          { label: training.title, to: `/trainings/${training.id}` },
          { label: module.title, to: `/trainings/${training.id}/modules/${module.id}` },
          { label: lesson.title },
        ]}
      />

      <ChalkTitle eyebrow={`Урок ${lesson.order} из модуля ${module.order}`} title={lesson.title} text={lesson.summary} />

      <div className="lesson-topline">
        <span className="status-pill ok">Доступ открыт</span>
        <span>Прогресс просмотра: {progressRatio(progress)}%</span>
        {nextLesson ? (
          <Link to={`/trainings/${training.id}/modules/${module.id}/lessons/${nextLesson.id}`}>Следующий урок</Link>
        ) : (
          <Link to={`/trainings/${training.id}/modules/${module.id}`}>Вернуться к модулю</Link>
        )}
      </div>

      <div className="video-board chalk-panel">
        <video ref={videoRef} controls src={lesson.videoUrl} onTimeUpdate={handleTimeUpdate} />
        <div className="action-row">
          <button
            className="chalk-button ghost"
            type="button"
            onClick={() => {
              if (videoRef.current && progress?.lastPositionSeconds) {
                videoRef.current.currentTime = progress.lastPositionSeconds;
                void videoRef.current.play();
              }
            }}
          >
            Продолжить
          </button>
          <button
            className="chalk-button ghost"
            type="button"
            onClick={() => {
              if (videoRef.current) {
                videoRef.current.currentTime = 0;
                void videoRef.current.play();
              }
            }}
          >
            Сначала
          </button>
        </div>
      </div>

      <div className="lesson-blocks">
        {blocks.map((block) => (
          <article className={`chalk-card lesson-block ${block.type}`} key={block.id}>
            <div className="lesson-block-head">
              {block.coverImage ? <img className="lesson-block-image" src={block.coverImage} alt="" loading="lazy" /> : null}
              <span className="chalk-eyebrow">{block.type === "checklist" ? "чеклист" : block.type === "cta" ? "действие" : "конспект"}</span>
            </div>
            <h3>{block.title}</h3>
            <p>{block.body}</p>
            {block.bullets.length ? (
              <ul>
                {block.bullets.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
          </article>
        ))}
      </div>

      <div className="subsection-head">
        <h2>Материалы урока</h2>
        <p>Файлы, шаблоны, инструкции и промпты привязаны к уроку как блоки конструктора.</p>
      </div>
      <div className="material-grid">
        {materials.map((material) => {
          const materialAccess = getMaterialAccess(material, currentUser);
          return <MaterialCard material={material} accessResult={materialAccess} key={material.id} />;
        })}
      </div>

      {template ? (
        <section className="chalk-panel homework-panel">
          <span className="chalk-eyebrow">домашнее задание</span>
          <h2>{template.title}</h2>
          <p>{template.prompt}</p>
          <div className="mini-list">
            {template.checklist.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
          <p className="homework-status">
            Статус: <strong>{formatHomeworkStatus(homework?.status || "not_submitted")}</strong>
          </p>
          {homework?.reviewerComment ? <p className="review-comment">Комментарий: {homework.reviewerComment}</p> : null}
          {homeworkAllowed ? (
            <form
              className="homework-form"
              onSubmit={(event) => {
                event.preventDefault();
                submitHomework(lesson.id, homeworkText, attachments);
              }}
            >
              <label>
                Ответ
                <textarea
                  value={homeworkText}
                  onChange={(event) => setHomeworkText(event.target.value)}
                  rows={5}
                  placeholder="Опишите выполненный артефакт и ссылку на работу."
                />
              </label>
              <label>
                Прикрепить файл
                <input type="file" multiple onChange={handleFiles} />
              </label>
              {isUploading ? <p className="homework-status">Файлы загружаются на сервер...</p> : null}
              {uploadError ? <p className="form-error">{uploadError}</p> : null}
              {attachments.length ? (
                <div className="mini-list">
                  {attachments.map((file) => (
                    <span key={`${file.name}-${file.size}`}>
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
              <button className="chalk-button" type="submit" disabled={isUploading}>
                {isUploading ? "Ждем файлы" : "Отправить домашку"}
              </button>
            </form>
          ) : (
            <p className="form-error">Проверка домашних доступна на тарифах с сопровождением.</p>
          )}
        </section>
      ) : null}
    </section>
  );
}
