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
  return `${prefix}-${Math.random().toString(36).slice(2, 8)}`;
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

function getLessonProgress(state: AppState, lessonId: string, studentId: string) {
  return state.progress.find((item) => item.lessonId === lessonId && item.studentId === studentId);
}

function previousLesson(state: AppState, lesson: Lesson) {
  const module = state.modules.find((item) => item.id === lesson.moduleId);
  if (!module) {
    return undefined;
  }
  const lessons = getLessonsForModule(state, module.id);
  const index = lessons.findIndex((item) => item.id === lesson.id);
  if (index <= 0) {
    return undefined;
  }
  return lessons[index - 1];
}

export function getAccessResult(
  entity: BaseEntity,
  user?: User,
  previousCompleted = true,
): AccessResult {
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
  if (!previousCompleted) {
    return {
      allowed: false,
      reason: "previous",
      message: "Нужно завершить предыдущий урок",
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
  const prev = user && lesson.accessPolicy.sequential ? previousLesson(state, lesson) : undefined;
  const previousCompleted = !prev || !user || Boolean(getLessonProgress(state, prev.id, user.id)?.isCompleted);
  return getAccessResult(lesson, user, previousCompleted);
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
  return state.progress.find((item) => item.lessonId === lessonId && item.studentId === studentId);
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
  return sortByOrder(
    state.folders.filter(
      (folder) =>
        folder.trainingId === trainingId &&
        folder.parentFolderId === parentFolderId &&
        folder.status !== "archived",
    ),
  );
}

export function getModulesForTraining(state: AppState, trainingId: string) {
  return sortByOrder(
    state.modules.filter((module) => module.trainingId === trainingId && module.status !== "archived"),
  );
}

export function getLessonsForModule(state: AppState, moduleId: string) {
  return sortByOrder(
    state.lessons.filter((lesson) => lesson.moduleId === moduleId && lesson.status !== "archived"),
  );
}

export function getMaterialsForParent(
  state: AppState,
  parentType: Material["parentType"],
  parentId: string,
) {
  return sortByOrder(
    state.materials.filter(
      (item) =>
        item.parentType === parentType && item.parentId === parentId && item.status !== "archived",
    ),
  );
}

export function getBlocksForLesson(state: AppState, lessonId: string) {
  return sortByOrder(state.lessonBlocks.filter((item) => item.lessonId === lessonId && item.status !== "archived"));
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
  return state.trainings.find((item) => item.id === trainingId);
}

export function getFolderById(state: AppState, folderId?: string) {
  return state.folders.find((item) => item.id === folderId);
}

export function getModuleById(state: AppState, moduleId?: string) {
  return state.modules.find((item) => item.id === moduleId);
}

export function getLessonById(state: AppState, lessonId?: string) {
  return state.lessons.find((item) => item.id === lessonId);
}

export function getUserById(state: AppState, userId?: string | null) {
  return state.users.find((item) => item.id === userId);
}

export function getNextLesson(state: AppState, lesson: Lesson) {
  const lessons = getLessonsForModule(state, lesson.moduleId);
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
