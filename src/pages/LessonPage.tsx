import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApp } from "../app/context";
import { fetchLessonPlaybackRequest } from "../domain/api";
import { lessonCompletionAcknowledgementText } from "../domain/legal";
import {
  AccessDeniedPanel,
  Breadcrumbs,
  ChalkTitle,
  LinkifiedText,
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
import type { HomeworkAttachment, LessonPlayback } from "../domain/types";

const kinescopeIframeApiUrl = "https://player.kinescope.io/latest/iframe.player.js";
const progressSaveIntervalMs = 10000;

interface KinescopePlayerEvent {
  data?: {
    currentTime?: number;
    percent?: number;
    error?: unknown;
  };
}

interface KinescopePlayer {
  Events: {
    Loaded: string;
    Pause: string;
    Ended: string;
    TimeUpdate: string;
    Error: string;
  };
  on: (event: string, handler: (event?: KinescopePlayerEvent) => void) => KinescopePlayer;
  off?: (event: string, handler: (event?: KinescopePlayerEvent) => void) => KinescopePlayer;
  getCurrentTime: () => Promise<number>;
  getDuration: () => Promise<number>;
  seekTo: (seconds: number) => Promise<void>;
}

interface KinescopePlayerFactory {
  create: (
    elementId: string,
    options: {
      url: string;
      size?: {
        width: string | number;
        height: string | number;
      };
    },
  ) => Promise<KinescopePlayer>;
}

declare global {
  interface Window {
    __kinescopePlayerFactory?: KinescopePlayerFactory;
    onKinescopeIframeAPIReady?: (playerFactory: KinescopePlayerFactory) => void;
  }
}

let kinescopeFactoryPromise: Promise<KinescopePlayerFactory> | null = null;

function loadKinescopePlayerFactory() {
  if (window.__kinescopePlayerFactory) {
    return Promise.resolve(window.__kinescopePlayerFactory);
  }
  if (kinescopeFactoryPromise) {
    return kinescopeFactoryPromise;
  }

  kinescopeFactoryPromise = new Promise<KinescopePlayerFactory>((resolve, reject) => {
    const previousReadyCallback = window.onKinescopeIframeAPIReady;
    const timeoutId = window.setTimeout(() => reject(new Error("Kinescope IFrame API load timed out")), 15000);
    window.onKinescopeIframeAPIReady = (playerFactory: KinescopePlayerFactory) => {
      window.clearTimeout(timeoutId);
      previousReadyCallback?.(playerFactory);
      window.__kinescopePlayerFactory = playerFactory;
      resolve(playerFactory);
    };

    const existingScript = document.querySelector<HTMLScriptElement>(`script[src="${kinescopeIframeApiUrl}"]`);
    if (existingScript) {
      existingScript.addEventListener("error", () => reject(new Error("Kinescope IFrame API load failed")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = kinescopeIframeApiUrl;
    script.async = true;
    script.addEventListener("error", () => reject(new Error("Kinescope IFrame API load failed")), { once: true });
    document.head.appendChild(script);
  });

  return kinescopeFactoryPromise.catch((error) => {
    kinescopeFactoryPromise = null;
    throw error;
  });
}

function safeSeconds(value: number) {
  return Math.max(0, Math.round(Number.isFinite(value) ? value : 0));
}

function kinescopePlayerUrl(playback: LessonPlayback) {
  if (!playback.embedUrl || !playback.videoId) {
    return playback.embedUrl || "";
  }
  try {
    const embedUrl = new URL(playback.embedUrl);
    const playerUrl = new URL(`/${encodeURIComponent(playback.videoId)}`, embedUrl.origin);
    embedUrl.searchParams.forEach((value, key) => playerUrl.searchParams.set(key, value));
    return playerUrl.toString();
  } catch {
    return playback.embedUrl;
  }
}

function formatTimecode(seconds: number) {
  const safeSeconds = Math.max(0, Math.round(seconds || 0));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const restSeconds = safeSeconds % 60;
  const minuteLabel = hours > 0 ? String(minutes).padStart(2, "0") : String(minutes);
  const secondLabel = String(restSeconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${minuteLabel}:${secondLabel}` : `${minuteLabel}:${secondLabel}`;
}

export function LessonPage() {
  const { trainingId, moduleId, lessonId } = useParams();
  const { state, currentUser, submitHomework, saveProgress, uploadHomeworkFiles } = useApp();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const kinescopePlayerRef = useRef<KinescopePlayer | null>(null);
  const progressSnapshotRef = useRef({ watchedSeconds: 0, durationSeconds: 0, lastPositionSeconds: 0 });
  const lastProgressSaveAtRef = useRef(0);
  const saveProgressRef = useRef(saveProgress);
  const training = getTrainingById(state, trainingId);
  const module = getModuleById(state, moduleId);
  const lesson = getLessonById(state, lessonId);
  const homework = currentUser && lesson ? getHomeworkForLesson(state, lesson.id, currentUser.id) : undefined;
  const progress = currentUser && lesson ? getProgressForLesson(state, lesson.id, currentUser.id) : undefined;
  const kinescopePlayerElementId = `kinescope-player-${String(lesson?.id || "empty").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const [homeworkText, setHomeworkText] = useState("");
  const [attachments, setAttachments] = useState<HomeworkAttachment[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [playback, setPlayback] = useState<LessonPlayback | null>(null);
  const [playbackError, setPlaybackError] = useState("");
  const [completionReady, setCompletionReady] = useState(false);
  const [completionAcknowledged, setCompletionAcknowledged] = useState(false);
  const [completionMessage, setCompletionMessage] = useState("");

  useEffect(() => {
    setHomeworkText(homework?.text ?? "");
    setAttachments([]);
  }, [homework?.id, homework?.text]);

  useEffect(() => {
    saveProgressRef.current = saveProgress;
  }, [saveProgress]);

  useEffect(() => {
    let isActive = true;
    setPlayback(null);
    setPlaybackError("");

    if (!lesson?.id || !currentUser) {
      return () => {
        isActive = false;
      };
    }

    void fetchLessonPlaybackRequest(lesson.id)
      .then((nextPlayback) => {
        if (isActive) {
          setPlayback(nextPlayback);
        }
      })
      .catch(() => {
        if (isActive) {
          setPlaybackError("Не удалось получить защищенный доступ к видео. Обновите страницу или проверьте настройки урока.");
        }
      });

    return () => {
      isActive = false;
    };
  }, [currentUser?.id, lesson?.id]);

  useEffect(() => {
    progressSnapshotRef.current = {
      watchedSeconds: progress?.watchedSeconds || 0,
      durationSeconds: progress?.durationSeconds || 0,
      lastPositionSeconds: progress?.lastPositionSeconds || 0,
    };
    lastProgressSaveAtRef.current = 0;
    setCompletionReady(Boolean(progress?.isCompleted || progressRatio(progress) >= 90));
    setCompletionAcknowledged(Boolean(progress?.isCompleted));
    setCompletionMessage("");
  }, [lesson?.id]);

  useEffect(() => {
    progressSnapshotRef.current = {
      watchedSeconds: Math.max(progressSnapshotRef.current.watchedSeconds, progress?.watchedSeconds || 0),
      durationSeconds: Math.max(progressSnapshotRef.current.durationSeconds, progress?.durationSeconds || 0),
      lastPositionSeconds: progress?.lastPositionSeconds || progressSnapshotRef.current.lastPositionSeconds,
    };
    if (progress?.isCompleted || progressRatio(progress) >= 90) {
      setCompletionReady(true);
    }
    if (progress?.isCompleted) {
      setCompletionAcknowledged(true);
    }
  }, [progress?.durationSeconds, progress?.isCompleted, progress?.lastPositionSeconds, progress?.watchedSeconds]);

  const savePlaybackProgress = useCallback(
    (
      nextProgress: {
        currentSeconds: number;
        durationSeconds: number;
        isCompleted?: boolean;
      },
      force = false,
    ) => {
      if (!lesson?.id || currentUser?.role !== "student") {
        return;
      }
      if (!playback?.playbackToken) {
        return;
      }

      const fallbackDuration = (lesson.durationMinutes || 0) * 60;
      const currentSeconds = safeSeconds(nextProgress.currentSeconds);
      const durationSeconds = safeSeconds(nextProgress.durationSeconds || fallbackDuration);
      const watchedSeconds = Math.max(progressSnapshotRef.current.watchedSeconds, currentSeconds);
      const wantsCompleted =
        Boolean(nextProgress.isCompleted) ||
        (currentSeconds > 0 && durationSeconds > 0 && currentSeconds / durationSeconds >= 0.9);
      const isCompleted = Boolean(progress?.isCompleted || (wantsCompleted && completionAcknowledged));

      if (wantsCompleted) {
        setCompletionReady(true);
      }

      progressSnapshotRef.current = {
        watchedSeconds,
        durationSeconds,
        lastPositionSeconds: currentSeconds,
      };

      const now = Date.now();
      if (!force && now - lastProgressSaveAtRef.current < progressSaveIntervalMs) {
        return;
      }

      lastProgressSaveAtRef.current = now;
      saveProgressRef.current(lesson.id, {
        watchedSeconds,
        durationSeconds,
        lastPositionSeconds: currentSeconds,
        isCompleted,
        completionAcknowledged: isCompleted,
        completionAcknowledgementText: isCompleted ? lessonCompletionAcknowledgementText : undefined,
      }, playback.playbackToken);
    },
    [completionAcknowledged, currentUser?.role, lesson?.durationMinutes, lesson?.id, playback?.playbackToken, progress?.isCompleted],
  );

  useEffect(() => {
    if (!lesson?.id || playback?.provider !== "kinescope" || !playback.embedUrl) {
      kinescopePlayerRef.current = null;
      return;
    }

    let isMounted = true;
    let player: KinescopePlayer | null = null;
    let durationSeconds = safeSeconds((playback.durationMinutes || lesson.durationMinutes) * 60);
    const handlers: Array<[string, (event?: KinescopePlayerEvent) => void]> = [];

    const rememberDuration = async () => {
      if (!player) {
        return durationSeconds;
      }
      try {
        const nextDuration = safeSeconds(await player.getDuration());
        if (nextDuration > 0) {
          durationSeconds = nextDuration;
        }
      } catch {
        // Kinescope returns duration only after player metadata is ready.
      }
      return durationSeconds;
    };

    void loadKinescopePlayerFactory()
      .then((playerFactory) => {
        if (!isMounted) {
          return undefined;
        }
        return playerFactory.create(kinescopePlayerElementId, {
          url: kinescopePlayerUrl(playback),
          size: { width: "100%", height: "100%" },
        });
      })
      .then((nextPlayer) => {
        if (!nextPlayer || !isMounted) {
          return;
        }
        player = nextPlayer;
        kinescopePlayerRef.current = nextPlayer;

        const onLoaded = () => {
          void rememberDuration();
        };
        const onTimeUpdate = (event?: KinescopePlayerEvent) => {
          const currentSeconds = safeSeconds(event?.data?.currentTime || 0);
          const percent = Number(event?.data?.percent || 0);
          if (!durationSeconds && currentSeconds > 0 && percent > 0) {
            durationSeconds = safeSeconds(currentSeconds / (percent / 100));
          }
          savePlaybackProgress({ currentSeconds, durationSeconds }, false);
        };
        const onPause = () => {
          void (async () => {
            const [currentSeconds, currentDuration] = await Promise.all([
              nextPlayer.getCurrentTime().catch(() => 0),
              rememberDuration(),
            ]);
            savePlaybackProgress({ currentSeconds, durationSeconds: currentDuration }, true);
          })();
        };
        const onEnded = () => {
          void (async () => {
            const currentDuration = await rememberDuration();
            savePlaybackProgress(
              {
                currentSeconds: currentDuration,
                durationSeconds: currentDuration,
                isCompleted: true,
              },
              true,
            );
          })();
        };
        const onError = () => {
          setPlaybackError("Не удалось загрузить плеер Kinescope. Обновите страницу или проверьте настройки урока.");
        };

        handlers.push(
          [nextPlayer.Events.Loaded, onLoaded],
          [nextPlayer.Events.TimeUpdate, onTimeUpdate],
          [nextPlayer.Events.Pause, onPause],
          [nextPlayer.Events.Ended, onEnded],
          [nextPlayer.Events.Error, onError],
        );
        handlers.forEach(([event, handler]) => nextPlayer.on(event, handler));
      })
      .catch(() => {
        if (isMounted) {
          setPlaybackError("Не удалось загрузить плеер Kinescope. Обновите страницу или проверьте настройки урока.");
        }
      });

    return () => {
      isMounted = false;
      if (player?.off) {
        handlers.forEach(([event, handler]) => player?.off?.(event, handler));
      }
      if (kinescopePlayerRef.current === player) {
        kinescopePlayerRef.current = null;
      }
    };
  }, [
    kinescopePlayerElementId,
    lesson?.durationMinutes,
    lesson?.id,
    playback?.durationMinutes,
    playback?.embedUrl,
    playback?.provider,
    playback?.videoId,
    savePlaybackProgress,
  ]);

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
  const nextLesson = getNextLesson(state, lesson);
  const nextLessonModule = nextLesson ? getModuleById(state, nextLesson.moduleId) : undefined;
  const nextLessonAccess = nextLesson ? getLessonAccess(state, nextLesson, currentUser) : undefined;
  const homeworkAllowed =
    currentUser?.role === "student" &&
    Boolean(template && currentUser.tariffId && template.requiredTariffIds.includes(currentUser.tariffId));
  const timecodes = [...(lesson.timecodes || [])]
    .filter((timecode) => timecode.label.trim())
    .sort((left, right) => left.seconds - right.seconds);

  const seekToTimecode = (seconds: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = Math.max(0, seconds);
      void videoRef.current.play();
      return;
    }
    if (kinescopePlayerRef.current) {
      void kinescopePlayerRef.current.seekTo(Math.max(0, seconds));
    }
  };

  const saveHtmlVideoProgress = (force = false) => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    savePlaybackProgress(
      {
        currentSeconds: video.currentTime,
        durationSeconds: video.duration || lesson.durationMinutes * 60,
        isCompleted: video.ended,
      },
      force,
    );
  };

  const handleTimeUpdate = () => {
    saveHtmlVideoProgress(false);
  };

  const confirmLessonCompletion = () => {
    if (!lesson?.id || currentUser?.role !== "student" || !playback?.playbackToken || !completionReady) {
      return;
    }
    const fallbackDuration = (lesson.durationMinutes || 0) * 60;
    const durationSeconds = Math.max(
      progressSnapshotRef.current.durationSeconds,
      progress?.durationSeconds || 0,
      fallbackDuration,
    );
    const watchedSeconds = Math.max(progressSnapshotRef.current.watchedSeconds, progress?.watchedSeconds || 0);
    const lastPositionSeconds = Math.max(
      progressSnapshotRef.current.lastPositionSeconds,
      progress?.lastPositionSeconds || 0,
    );
    saveProgress(lesson.id, {
      watchedSeconds,
      durationSeconds,
      lastPositionSeconds,
      isCompleted: true,
      completionAcknowledged: true,
      completionAcknowledgementText: lessonCompletionAcknowledgementText,
    }, playback.playbackToken);
    setCompletionAcknowledged(true);
    setCompletionMessage("Урок подтвержден. Если следующий урок уже открыт по расписанию, можно переходить дальше.");
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
        {nextLesson && nextLessonModule ? (
          nextLessonAccess?.allowed ? (
            <Link to={`/trainings/${nextLessonModule.trainingId}/modules/${nextLessonModule.id}/lessons/${nextLesson.id}`}>
              Следующий урок
            </Link>
          ) : (
            <span className="lesson-next-locked">{nextLessonAccess?.message || "Следующий урок пока закрыт"}</span>
          )
        ) : (
          <Link to={`/trainings/${training.id}/modules/${module.id}`}>Вернуться к модулю</Link>
        )}
      </div>

      <div className="video-board chalk-panel">
        {playback?.provider === "kinescope" ? (
          playback.embedUrl ? (
            <div className="kinescope-player" title={lesson.title}>
              <div className="kinescope-player-mount" id={kinescopePlayerElementId} />
            </div>
          ) : (
            <div className="video-empty-state">{playback.message || "Для урока не указан ID видео Kinescope."}</div>
          )
        ) : playbackError ? (
          <div className="video-empty-state">{playbackError}</div>
        ) : playback ? (
          <video
            ref={videoRef}
            controls
            src={playback.videoUrl || lesson.videoUrl}
            onEnded={() => saveHtmlVideoProgress(true)}
            onPause={() => saveHtmlVideoProgress(true)}
            onTimeUpdate={handleTimeUpdate}
          />
        ) : (
          <div className="video-empty-state">Получаем защищенный доступ к видео...</div>
        )}

        {playback?.provider === "kinescope" ? null : (
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
        )}

        {timecodes.length ? (
          <div className="timecode-list" aria-label="Таймкоды урока">
            <strong>Таймкоды</strong>
            <div className="timecode-items">
              {timecodes.map((timecode) => (
                <button className="timecode-item" type="button" onClick={() => seekToTimecode(timecode.seconds)} key={timecode.id}>
                  <span>{formatTimecode(timecode.seconds)}</span>
                  <strong>{timecode.label}</strong>
                  {timecode.note ? <small>{timecode.note}</small> : null}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      {currentUser?.role === "student" ? (
        <section className="chalk-panel lesson-completion-panel">
          <div>
            <span className="chalk-eyebrow">завершение урока</span>
            <h2>{progress?.isCompleted ? "Урок подтвержден" : "Подтверди прохождение урока"}</h2>
            <p>
              После просмотра урока отметь, что материал изучен и доступ к уроку был предоставлен корректно. Это
              подтверждение относится только к текущему уроку, юридические документы повторно принимать не нужно.
            </p>
          </div>
          <label className="legal-consent lesson-confirmation-consent" htmlFor={`lesson-confirmation-${lesson.id}`}>
            <input
              id={`lesson-confirmation-${lesson.id}`}
              type="checkbox"
              checked={completionAcknowledged}
              disabled={Boolean(progress?.isCompleted) || !completionReady}
              onChange={(event) => {
                setCompletionAcknowledged(event.target.checked);
                setCompletionMessage("");
              }}
            />
            <span>{lessonCompletionAcknowledgementText}</span>
          </label>
          {!completionReady ? (
            <p className="lesson-confirmation-hint">Кнопка станет доступна после просмотра не меньше 90% видео.</p>
          ) : null}
          {completionMessage ? <p className="checkout-success">{completionMessage}</p> : null}
          <button
            className="chalk-button"
            type="button"
            disabled={Boolean(progress?.isCompleted) || !completionReady || !completionAcknowledged}
            onClick={confirmLessonCompletion}
          >
            {progress?.isCompleted ? "Подтверждено" : "Завершить урок"}
          </button>
        </section>
      ) : null}

      <div className="lesson-blocks">
        {blocks.map((block) => (
          <article className={`chalk-card lesson-block ${block.type}`} key={block.id}>
            <div className="lesson-block-head">
              {block.coverImage ? <img className="lesson-block-image" src={block.coverImage} alt="" loading="lazy" /> : null}
              <span className="chalk-eyebrow">{block.type === "checklist" ? "чеклист" : block.type === "cta" ? "действие" : "конспект"}</span>
            </div>
            <h3>{block.title}</h3>
            <p><LinkifiedText text={block.body} /></p>
            {block.bullets.length ? (
              <ul>
                {block.bullets.map((item) => (
                  <li key={item}><LinkifiedText text={item} /></li>
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
          <p><LinkifiedText text={template.prompt} /></p>
          <div className="mini-list">
            {template.checklist.map((item) => (
              <span key={item}><LinkifiedText text={item} /></span>
            ))}
          </div>
          <p className="homework-status">
            Статус: <strong>{formatHomeworkStatus(homework?.status || "not_submitted")}</strong>
          </p>
          {homework?.reviewerComment ? <p className="review-comment">Комментарий: <LinkifiedText text={homework.reviewerComment} /></p> : null}
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
                <input
                  type="file"
                  accept=".pdf,.txt,.md,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.png,.jpg,.jpeg,.webp,.gif,.mp4,.mov,.m4v,.webm"
                  multiple
                  onChange={handleFiles}
                />
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
