import type {
  AccessPolicy,
  AccessResult,
  AppState,
  BaseEntity,
  Folder,
  HomeworkStatus,
  Lesson,
  LessonProgress,
  Material,
  Module,
  TariffId,
  Training,
  User,
} from "./types";

const COVER_LIBRARY: Record<string, string> = {
  ladder: "M26 164 L26 26 L150 26 M52 52 L116 52 M52 92 L116 92 M52 132 L116 132 M164 34 C196 22 228 28 242 54 C254 80 236 110 202 124 C170 136 144 154 140 184",
  radar: "M134 24 A110 110 0 1 1 133.8 24 M134 52 A82 82 0 1 1 133.8 52 M134 80 A54 54 0 1 1 133.8 80 M134 24 L134 188 M24 106 L244 106 M134 106 L198 60",
  network: "M32 148 L84 58 L156 94 L226 40 M84 58 L128 168 L226 40 M48 190 L128 168 L226 162 M156 94 L214 204",
  funnel: "M32 34 L236 34 L178 108 L178 182 L118 210 L118 108 Z M74 72 H194",
  squares: "M38 40 H110 V112 H38 Z M154 40 H226 V112 H154 Z M38 126 H110 V198 H38 Z M154 126 H226 V198 H154 Z M110 76 H154 M74 112 V126 M190 112 V126",
  constellation: "M30 42 L78 74 L132 48 L178 88 L224 54 M62 162 L104 126 L164 152 L214 126 M40 204 L90 182 L132 204 L206 182",
  brief: "M34 46 H232 V198 H34 Z M34 86 H232 M82 46 V18 H184 V46 M68 122 H196 M68 150 H196 M68 178 H164",
  notebook: "M44 30 H224 V204 H44 Z M74 54 H198 M74 92 H198 M74 130 H198 M74 168 H150",
};

export function buildCoverImage(title: string, style: string) {
  const path = COVER_LIBRARY[style] ?? COVER_LIBRARY.notebook;
  const safeTitle = escapeXml(title.toUpperCase());
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 230" fill="none"><rect width="260" height="230" rx="20" fill="#11110f"/><path d="${path}" stroke="#F4F0E6" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/><text x="22" y="214" fill="#F4F0E6" font-size="18" font-family="Trebuchet MS, sans-serif" letter-spacing="2">${safeTitle}</text></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export function sortByOrder<T extends { order: number }>(items: T[]) {
  return [...items].sort((left, right) => left.order - right.order);
}

export function createId(prefix: string) {
  if (globalThis.crypto?.randomUUID) {
    return `${prefix}-${globalThis.crypto.randomUUID()}`;
  }
  if (globalThis.crypto?.getRandomValues) {
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    return `${prefix}-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
  }
  return `${prefix}-${Date.now().toString(36)}`;
}

export function escapeXml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

export function ensureCover<T extends BaseEntity>(entity: T): T {
  return {
    ...entity,
    coverImage: entity.coverImage || buildCoverImage(entity.title, entity.coverStyle),
  };
}

export function refreshCover<T extends BaseEntity>(entity: T): T {
  return {
    ...entity,
    coverImage: buildCoverImage(entity.title, entity.coverStyle),
  };
}

export function isPublished(entity: { status: string }) {
  return entity.status === "published";
}

export function formatHomeworkStatus(status: HomeworkStatus) {
  switch (status) {
    case "not_submitted":
      return "Не отправлена";
    case "submitted":
      return "Отправлена";
    case "in_review":
      return "На проверке";
    case "accepted":
      return "Принята";
    case "revision":
      return "Нужна доработка";
    default:
      return status;
  }
}

export function canAccessByPolicy(policy: AccessPolicy, tariffId?: TariffId) {
  if (policy.tariffIds.length === 0) {
    return true;
  }
  if (!tariffId) {
    return false;
  }
  return policy.tariffIds.includes(tariffId);
}

export function isExpired(user?: User) {
  if (!user?.expiresAt) {
    return false;
  }
  return Date.parse(user.expiresAt) < Date.now();
}

const fallbackStudentStartAt = "2026-05-07T00:00:00.000Z";
const hourMs = 60 * 60 * 1000;

interface LessonUnlockInfo {
  timeUnlocked: boolean;
  availableAt?: string;
  previousLesson?: Lesson;
  previousTimeUnlocked: boolean;
  previousAvailableAt?: string;
}

interface StateIndex {
  trainingsById: Map<string, Training>;
  foldersById: Map<string, Folder>;
  modulesById: Map<string, Module>;
  lessonsById: Map<string, Lesson>;
  usersById: Map<string, User>;
  foldersByTrainingParent: Map<string, Folder[]>;
  modulesByTraining: Map<string, Module[]>;
  lessonsByModule: Map<string, Lesson[]>;
  materialsByParent: Map<string, Material[]>;
  blocksByLesson: Map<string, AppState["lessonBlocks"]>;
  progressByStudentLesson: Map<string, LessonProgress>;
  trainingLessons: Map<string, Lesson[]>;
}

const stateIndexCache = new WeakMap<AppState, StateIndex>();

function mapById<T extends { id: string }>(items: T[]) {
  return new Map(items.map((item) => [item.id, item]));
}

function appendToIndex<T>(index: Map<string, T[]>, key: string, item: T) {
  const current = index.get(key);
  if (current) {
    current.push(item);
  } else {
    index.set(key, [item]);
  }
}

function folderParentKey(trainingId: string, parentFolderId: string | null = null) {
  return `${trainingId}::${parentFolderId || ""}`;
}

function materialParentKey(parentType: Material["parentType"], parentId: string) {
  return `${parentType}:${parentId}`;
}

function progressKey(studentId: string, lessonId: string) {
  return `${studentId}:${lessonId}`;
}

function getStateIndex(state: AppState) {
  const cached = stateIndexCache.get(state);
  if (cached) {
    return cached;
  }

  const foldersByTrainingParent = new Map<string, Folder[]>();
  for (const folder of state.folders) {
    if (folder.status !== "archived") {
      appendToIndex(foldersByTrainingParent, folderParentKey(folder.trainingId, folder.parentFolderId), folder);
    }
  }

  const modulesByTraining = new Map<string, Module[]>();
  for (const module of state.modules) {
    if (module.status !== "archived") {
      appendToIndex(modulesByTraining, module.trainingId, module);
    }
  }

  const lessonsByModule = new Map<string, Lesson[]>();
  for (const lesson of state.lessons) {
    if (lesson.status !== "archived") {
      appendToIndex(lessonsByModule, lesson.moduleId, lesson);
    }
  }

  const materialsByParent = new Map<string, Material[]>();
  for (const material of state.materials) {
    if (material.status !== "archived") {
      appendToIndex(materialsByParent, materialParentKey(material.parentType, material.parentId), material);
    }
  }

  const blocksByLesson = new Map<string, AppState["lessonBlocks"]>();
  for (const block of state.lessonBlocks) {
    if (block.status !== "archived") {
      appendToIndex(blocksByLesson, block.lessonId, block);
    }
  }

  const progressByStudentLesson = new Map<string, LessonProgress>();
  for (const progress of state.progress) {
    progressByStudentLesson.set(progressKey(progress.studentId, progress.lessonId), progress);
  }

  const index: StateIndex = {
    trainingsById: mapById(state.trainings),
    foldersById: mapById(state.folders),
    modulesById: mapById(state.modules),
    lessonsById: mapById(state.lessons),
    usersById: mapById(state.users),
    foldersByTrainingParent,
    modulesByTraining,
    lessonsByModule,
    materialsByParent,
    blocksByLesson,
    progressByStudentLesson,
    trainingLessons: new Map(),
  };

  for (const folders of foldersByTrainingParent.values()) {
    folders.sort((left, right) => left.order - right.order);
  }
  for (const modules of modulesByTraining.values()) {
    modules.sort((left, right) => left.order - right.order);
  }
  for (const lessons of lessonsByModule.values()) {
    lessons.sort((left, right) => left.order - right.order);
  }
  for (const materials of materialsByParent.values()) {
    materials.sort((left, right) => left.order - right.order);
  }
  for (const blocks of blocksByLesson.values()) {
    blocks.sort((left, right) => left.order - right.order);
  }

  stateIndexCache.set(state, index);
  return index;
}

function getLessonProgress(state: AppState, lessonId: string, studentId: string) {
  return getStateIndex(state).progressByStudentLesson.get(progressKey(studentId, lessonId));
}

function getTrainingForLesson(state: AppState, lesson: Lesson) {
  const index = getStateIndex(state);
  const module = index.modulesById.get(lesson.moduleId);
  if (!module) {
    return undefined;
  }
  return index.trainingsById.get(module.trainingId);
}

export function getTrainingLessonsInOrder(state: AppState, trainingId: string) {
  const index = getStateIndex(state);
  const cached = index.trainingLessons.get(trainingId);
  if (cached) {
    return cached;
  }
  const lessons = (index.modulesByTraining.get(trainingId) || []).flatMap((module) => index.lessonsByModule.get(module.id) || []);
  index.trainingLessons.set(trainingId, lessons);
  return lessons;
}

export function getPreviousLesson(state: AppState, lesson: Lesson) {
  const training = getTrainingForLesson(state, lesson);
  if (!training) {
    return undefined;
  }
  const lessons = getTrainingLessonsInOrder(state, training.id);
  const index = lessons.findIndex((item) => item.id === lesson.id);
  if (index <= 0) {
    return undefined;
  }
  return lessons[index - 1];
}

function getStudentStartMs(user?: User) {
  const parsed = Date.parse(user?.createdAt || fallbackStudentStartAt);
  return Number.isFinite(parsed) ? parsed : Date.parse(fallbackStudentStartAt);
}

function getLessonDelayMs(lesson: Lesson) {
  return Math.max(0, Number(lesson.unlockDelayHours || 0)) * hourMs;
}

export function formatRemainingUntil(value?: string, nowMs = Date.now()) {
  if (!value) {
    return "";
  }
  const targetMs = Date.parse(value);
  if (!Number.isFinite(targetMs)) {
    return "";
  }
  const totalMinutes = Math.max(0, Math.ceil((targetMs - nowMs) / 60000));
  if (totalMinutes <= 0) {
    return "уже открыто";
  }
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  const parts = [];
  if (days) {
    parts.push(`${days} д`);
  }
  if (hours) {
    parts.push(`${hours} ч`);
  }
  if (minutes || parts.length === 0) {
    parts.push(`${minutes} мин`);
  }
  return parts.join(" ");
}

export function getLessonUnlockInfo(state: AppState, lesson: Lesson, user?: User): LessonUnlockInfo {
  if (!user || user.role !== "student") {
    return {
      timeUnlocked: true,
      previousTimeUnlocked: true,
    };
  }
  const training = getTrainingForLesson(state, lesson);
  if (!training) {
    return {
      timeUnlocked: true,
      previousTimeUnlocked: true,
    };
  }
  const lessons = getTrainingLessonsInOrder(state, training.id);
  let unlockMs = getStudentStartMs(user);
  let previousLessonItem: Lesson | undefined;
  let previousAvailableAt: string | undefined;

  for (const item of lessons) {
    unlockMs += getLessonDelayMs(item);
    const availableAt = new Date(unlockMs).toISOString();
    if (item.id === lesson.id) {
      const previousMs = previousAvailableAt ? Date.parse(previousAvailableAt) : undefined;
      return {
        timeUnlocked: unlockMs <= Date.now(),
        availableAt,
        previousLesson: previousLessonItem,
        previousTimeUnlocked: !previousMs || previousMs <= Date.now(),
        previousAvailableAt,
      };
    }
    previousLessonItem = item;
    previousAvailableAt = availableAt;
  }

  return {
    timeUnlocked: true,
    previousTimeUnlocked: true,
  };
}

export function getAccessResult(
  entity: BaseEntity,
  user?: User,
  previousCompletedOrOptions:
    | boolean
    | {
        previousCompleted?: boolean;
        previousLessonTitle?: string;
        unlockInfo?: LessonUnlockInfo;
      } = true,
): AccessResult {
  const options =
    typeof previousCompletedOrOptions === "boolean"
      ? { previousCompleted: previousCompletedOrOptions }
      : previousCompletedOrOptions;
  const previousCompleted = options.previousCompleted ?? true;
  if (!user) {
    return {
      allowed: false,
      reason: "login",
      message: "Нужно войти",
    };
  }
  if (isExpired(user)) {
    return {
      allowed: false,
      reason: "expired",
      message: "Доступ истек",
    };
  }
  if (user.role !== "student") {
    return {
      allowed: true,
      reason: "ok",
      message: "Доступ открыт",
    };
  }
  if (!isPublished(entity)) {
    return {
      allowed: false,
      reason: "unpublished",
      message: "Материал еще не опубликован",
    };
  }
  if (!canAccessByPolicy(entity.accessPolicy, user.tariffId)) {
    return {
      allowed: false,
      reason: "tariff",
      message: "Недоступно на вашем тарифе",
    };
  }
  if (options.unlockInfo && !options.unlockInfo.previousTimeUnlocked) {
    const dependsOnTitle = options.unlockInfo.previousLesson?.title || "предыдущий урок";
    const dependsOnAvailableAt = options.unlockInfo.previousAvailableAt;
    const remaining = formatRemainingUntil(dependsOnAvailableAt);
    return {
      allowed: false,
      reason: "previous_time",
      message: `Сначала по расписанию должен открыться урок «${dependsOnTitle}»${
        dependsOnAvailableAt ? `: ${readableDate(dependsOnAvailableAt)}` : ""
      }${remaining ? `, осталось ${remaining}` : ""}`,
      availableAt: options.unlockInfo.availableAt,
      dependsOnLessonTitle: dependsOnTitle,
      dependsOnAvailableAt,
    };
  }
  if (options.unlockInfo && !options.unlockInfo.timeUnlocked) {
    const remaining = formatRemainingUntil(options.unlockInfo.availableAt);
    return {
      allowed: false,
      reason: "time",
      message: `Откроется по расписанию: ${readableDate(options.unlockInfo.availableAt)}${
        remaining ? `, осталось ${remaining}` : ""
      }`,
      availableAt: options.unlockInfo.availableAt,
      dependsOnLessonTitle: options.unlockInfo.previousLesson?.title,
      dependsOnAvailableAt: options.unlockInfo.previousAvailableAt,
    };
  }
  if (!previousCompleted) {
    return {
      allowed: false,
      reason: "previous",
      message: options.previousLessonTitle
        ? `Сначала завершите предыдущий урок: «${options.previousLessonTitle}»`
        : "Нужно завершить предыдущий урок",
      dependsOnLessonTitle: options.previousLessonTitle,
    };
  }
  return {
    allowed: true,
    reason: "ok",
    message: "Доступ открыт",
  };
}

export function getTrainingAccess(state: AppState, training: Training, user?: User) {
  return getAccessResult(training, user);
}

export function getModuleAccess(state: AppState, module: Module, user?: User) {
  return getAccessResult(module, user);
}

export function getLessonAccess(state: AppState, lesson: Lesson, user?: User) {
  const prev = user ? getPreviousLesson(state, lesson) : undefined;
  const previousCompleted = !prev || !user || Boolean(getLessonProgress(state, prev.id, user.id)?.isCompleted);
  return getAccessResult(lesson, user, {
    previousCompleted,
    previousLessonTitle: prev?.title,
    unlockInfo: getLessonUnlockInfo(state, lesson, user),
  });
}

export function getFolderAccess(folder: Folder, user?: User) {
  return getAccessResult(folder, user);
}

export function getMaterialAccess(material: Material, user?: User) {
  return getAccessResult(material, user);
}

export function shouldShowLocked(entity: BaseEntity) {
  return entity.accessPolicy.visibility === "show_locked";
}

export function getProgressForLesson(state: AppState, lessonId: string, studentId: string) {
  return getLessonProgress(state, lessonId, studentId);
}

export function getHomeworkForLesson(state: AppState, lessonId: string, studentId: string) {
  return state.homeworkAnswers.find((item) => item.lessonId === lessonId && item.studentId === studentId);
}

export function getUserTrainings(state: AppState, user?: User) {
  if (!user) {
    return [];
  }
  if (user.role !== "student") {
    return sortByOrder(state.trainings.filter((item) => item.status !== "archived"));
  }
  return sortByOrder(
    state.trainings.filter((training) => {
      const access = getTrainingAccess(state, training, user);
      return access.allowed;
    }),
  );
}

export function getFoldersForTraining(state: AppState, trainingId: string, parentFolderId: string | null = null) {
  return getStateIndex(state).foldersByTrainingParent.get(folderParentKey(trainingId, parentFolderId)) || [];
}

export function getModulesForTraining(state: AppState, trainingId: string) {
  return getStateIndex(state).modulesByTraining.get(trainingId) || [];
}

export function getLessonsForModule(state: AppState, moduleId: string) {
  return getStateIndex(state).lessonsByModule.get(moduleId) || [];
}

export function getMaterialsForParent(
  state: AppState,
  parentType: Material["parentType"],
  parentId: string,
) {
  return getStateIndex(state).materialsByParent.get(materialParentKey(parentType, parentId)) || [];
}

export function getBlocksForLesson(state: AppState, lessonId: string) {
  return getStateIndex(state).blocksByLesson.get(lessonId) || [];
}

export function getPublishedLessonCount(state: AppState, trainingId: string) {
  const modules = state.modules.filter(
    (module) => module.trainingId === trainingId && module.status === "published",
  );
  return modules.reduce((sum, module) => {
    return (
      sum +
      state.lessons.filter(
        (lesson) => lesson.moduleId === module.id && lesson.status === "published",
      ).length
    );
  }, 0);
}

export function getTrainingById(state: AppState, trainingId?: string) {
  return trainingId ? getStateIndex(state).trainingsById.get(trainingId) : undefined;
}

export function getFolderById(state: AppState, folderId?: string) {
  return folderId ? getStateIndex(state).foldersById.get(folderId) : undefined;
}

export function getModuleById(state: AppState, moduleId?: string) {
  return moduleId ? getStateIndex(state).modulesById.get(moduleId) : undefined;
}

export function getLessonById(state: AppState, lessonId?: string) {
  return lessonId ? getStateIndex(state).lessonsById.get(lessonId) : undefined;
}

export function getUserById(state: AppState, userId?: string | null) {
  return userId ? getStateIndex(state).usersById.get(userId) : undefined;
}

export function getNextLesson(state: AppState, lesson: Lesson) {
  const training = getTrainingForLesson(state, lesson);
  const lessons = training ? getTrainingLessonsInOrder(state, training.id) : getLessonsForModule(state, lesson.moduleId);
  const index = lessons.findIndex((item) => item.id === lesson.id);
  if (index === -1 || index === lessons.length - 1) {
    return undefined;
  }
  return lessons[index + 1];
}

export function formatDuration(minutes: number) {
  return `${minutes} мин`;
}

export function progressRatio(progress?: LessonProgress) {
  if (!progress || progress.durationSeconds <= 0) {
    return 0;
  }
  return Math.min(100, Math.round((progress.watchedSeconds / progress.durationSeconds) * 100));
}

export function moduleProgressRatio(state: AppState, moduleId: string, studentId?: string) {
  if (!studentId) {
    return 0;
  }
  const lessons = getLessonsForModule(state, moduleId).filter((lesson) => lesson.status === "published");
  if (!lessons.length) {
    return 0;
  }
  const totalProgress = lessons.reduce((sum, lesson) => {
    return sum + progressRatio(getProgressForLesson(state, lesson.id, studentId));
  }, 0);
  return Math.round(totalProgress / lessons.length);
}

export function readableDate(value?: string | null) {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
