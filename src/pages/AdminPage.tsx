import { useEffect, useMemo, useState, type ChangeEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../app/context";
import { AccessDeniedPanel, ChalkTitle, EntityCover, TariffBadges } from "../components/ui";
import {
  createId,
  getBlocksForLesson,
  getFoldersForTraining,
  getLessonsForModule,
  getMaterialsForParent,
  getModulesForTraining,
} from "../domain/helpers";
import type {
  AccessPolicy,
  Folder,
  FolderKind,
  HomeworkTemplate,
  Lesson,
  LessonBlock,
  LessonBlockType,
  LessonTimecode,
  Material,
  MaterialType,
  Module,
  PublishStatus,
  Tariff,
  TariffId,
  Training,
  VideoProvider,
} from "../domain/types";

const tariffIds: TariffId[] = ["zero", "workshop", "basic", "mentor", "vip"];
const materialTypes: MaterialType[] = ["text", "template", "prompt", "link", "file", "embed"];
const lessonBlockTypes: LessonBlockType[] = ["text", "checklist", "quote", "cta"];

const videoProviderLabels: Record<VideoProvider, string> = {
  external: "Прямая ссылка / демо-видео",
  kinescope: "Kinescope",
};

const statusLabels: Record<PublishStatus, string> = {
  draft: "Черновик",
  published: "Опубликовано",
  archived: "В архиве",
};

const tariffLabels: Record<TariffId, string> = {
  zero: "Нулевой урок",
  workshop: "Воркшоп",
  basic: "Базовый",
  mentor: "С ментором",
  vip: "VIP",
};

const materialTypeLabels: Record<MaterialType, string> = {
  text: "Текст",
  template: "Шаблон",
  prompt: "Промпт",
  link: "Ссылка",
  file: "Файл",
  embed: "Встраиваемый блок",
};

const lessonBlockTypeLabels: Record<LessonBlockType, string> = {
  text: "Текст",
  checklist: "Чеклист",
  quote: "Цитата",
  cta: "Действие",
};

const totalLabels = {
  trainings: "тренинги",
  folders: "папки",
  modules: "модули",
  lessons: "уроки",
  materials: "материалы",
  homeworks: "домашки",
};

const homeworkTariffOptions: Array<{ value: string; label: string }> = [
  { value: "zero", label: "Только нулевой урок" },
  { value: "mentor,vip", label: "С ментором + VIP" },
  { value: "vip", label: "Только VIP" },
  { value: "basic,mentor,vip", label: "Базовый + С ментором + VIP" },
  { value: "zero,workshop,basic,mentor,vip", label: "Все тарифы" },
];

const adminGuideSteps = [
  {
    title: "Выбери тренинг",
    text: "Все папки, модули и уроки ниже относятся к выбранному тренингу.",
  },
  {
    title: "Собери структуру",
    text: "Сначала папки и модули, потом уроки, материалы, блоки урока и домашки.",
  },
  {
    title: "Поставь статус",
    text: "Ученики видят опубликованные элементы. Черновики оставь для подготовки.",
  },
  {
    title: "Проверь как ученик",
    text: "После правок открой тренинг или урок и проверь вид с нужного тарифа.",
  },
];

const adminQuickLinks = [
  { href: "#admin-tariffs", label: "Тарифы" },
  { href: "#admin-training", label: "Тренинг" },
  { href: "#admin-folders", label: "Папки и материалы" },
  { href: "#admin-program", label: "Модули и уроки" },
  { href: "#admin-reset", label: "Сброс" },
];

function defaultPolicy(tariffs: TariffId[], note: string): AccessPolicy {
  return {
    tariffIds: tariffs,
    visibility: "show_locked",
    sequential: false,
    durationMode: "rolling",
    durationDays: null,
    note,
  };
}

function toggleTariff(policy: AccessPolicy, tariffId: TariffId): AccessPolicy {
  const hasTariff = policy.tariffIds.includes(tariffId);
  return {
    ...policy,
    tariffIds: hasTariff
      ? policy.tariffIds.filter((item) => item !== tariffId)
      : [...policy.tariffIds, tariffId],
  };
}

function parseChecklist(value: string) {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseTimeInput(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return 0;
  }
  if (!trimmed.includes(":")) {
    return Math.max(0, Math.round(Number(trimmed) || 0));
  }
  const parts = trimmed.split(":").map((part) => Number(part.trim()));
  if (parts.some((part) => Number.isNaN(part))) {
    return 0;
  }
  return Math.max(0, parts.reduce((total, part) => total * 60 + part, 0));
}

function formatTimeInput(seconds: number) {
  const safeSeconds = Math.max(0, Math.round(seconds || 0));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const restSeconds = safeSeconds % 60;
  const minuteLabel = hours > 0 ? String(minutes).padStart(2, "0") : String(minutes);
  const secondLabel = String(restSeconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${minuteLabel}:${secondLabel}` : `${minuteLabel}:${secondLabel}`;
}

function materialContentValue(material: Material) {
  return material.materialType === "link" || material.materialType === "file" || material.materialType === "embed"
    ? material.url || ""
    : material.body || "";
}

function materialContentPlaceholder(material: Material) {
  if (material.materialType === "file") {
    return "Ссылка на файл или загрузите файл кнопкой ниже";
  }
  if (material.materialType === "link" || material.materialType === "embed") {
    return "Вставь ссылку";
  }
  return "Вставь текст материала. Ссылки вида https://... станут кликабельными у ученика.";
}

function formatFileSize(size?: number) {
  if (!size) {
    return "";
  }
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} КБ`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} МБ`;
}

function formatFolderOption(folder: Folder) {
  return `${folder.parentFolderId ? "↳ " : ""}${folder.title}`;
}

function AdminHint({ children }: { children: ReactNode }) {
  return <p className="admin-hint">{children}</p>;
}

function FieldHelp({ children }: { children: ReactNode }) {
  return <span className="field-help">{children}</span>;
}

function PreviewLink({ to, children = "Смотреть на сайте" }: { to: string; children?: ReactNode }) {
  return (
    <Link className="chalk-button ghost admin-preview-link" to={to}>
      {children}
    </Link>
  );
}

function ArchiveButton({
  title,
  entityLabel,
  onConfirm,
  children = "Удалить из показа",
  description = "Элемент уйдет в архив и пропадет у учеников. Данные останутся в локальном файле, чтобы их можно было восстановить вручную.",
}: {
  title: string;
  entityLabel: string;
  onConfirm: () => void;
  children?: ReactNode;
  description?: string;
}) {
  const handleClick = () => {
    const confirmed = window.confirm(
      `Удалить из показа ${entityLabel.toLowerCase()} «${title}»?\n\n${description}`,
    );
    if (confirmed) {
      onConfirm();
    }
  };

  return (
    <button className="chalk-button ghost danger-button" type="button" onClick={handleClick}>
      {children}
    </button>
  );
}

function PolicyEditor({
  policy,
  onChange,
  compact = false,
}: {
  policy: AccessPolicy;
  onChange: (policy: AccessPolicy) => void;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "policy-editor compact-policy" : "policy-editor"}>
      <div className="policy-caption">
        <strong>Доступ</strong>
        <span>Отметь тарифы, которым открыт этот блок.</span>
      </div>
      <div className="checkbox-line">
        {tariffIds.map((tariffId) => (
          <label key={tariffId}>
            <input
              type="checkbox"
              checked={policy.tariffIds.includes(tariffId)}
              onChange={() => onChange(toggleTariff(policy, tariffId))}
            />
            {tariffLabels[tariffId]}
          </label>
        ))}
      </div>
      <label>
        Видимость закрытого
        <select
          value={policy.visibility}
          onChange={(event) => onChange({ ...policy, visibility: event.target.value as AccessPolicy["visibility"] })}
        >
          <option value="show_locked">показать замком</option>
          <option value="hide">скрыть полностью</option>
        </select>
      </label>
    </div>
  );
}

export function AdminPage() {
  const { state, currentUser, saveEntity, archiveEntity, resetState, uploadCoverImage, uploadMaterialFile } = useApp();
  const [trainingId, setTrainingId] = useState(state.trainings[0]?.id || "");
  const [newTrainingTitle, setNewTrainingTitle] = useState("");
  const [newFolderTitle, setNewFolderTitle] = useState("");
  const [newFolderKind, setNewFolderKind] = useState<FolderKind>("folder");
  const [newFolderParentId, setNewFolderParentId] = useState("");
  const [newFolderUrl, setNewFolderUrl] = useState("");
  const [newMaterialTitle, setNewMaterialTitle] = useState("");
  const [newMaterialType, setNewMaterialType] = useState<MaterialType>("text");
  const [materialFolderId, setMaterialFolderId] = useState("");
  const [newModuleTitle, setNewModuleTitle] = useState("");
  const [newLessonTitle, setNewLessonTitle] = useState("");
  const [coverUploadState, setCoverUploadState] = useState<Record<string, string>>({});
  const [materialUploadState, setMaterialUploadState] = useState<Record<string, string>>({});

  const selectedTraining = state.trainings.find((item) => item.id === trainingId) || state.trainings[0];
  const trainingFolders = selectedTraining
    ? [...state.folders]
        .filter((folder) => folder.trainingId === selectedTraining.id && folder.status !== "archived")
        .sort((left, right) => left.order - right.order)
    : [];
  const modules = selectedTraining ? getModulesForTraining(state, selectedTraining.id) : [];
  const [lessonModuleId, setLessonModuleId] = useState(modules[0]?.id || "");
  const activeLessonModuleId = lessonModuleId || modules[0]?.id || "";
  const activeMaterialFolderId = materialFolderId || trainingFolders[0]?.id || "";

  useEffect(() => {
    if (!selectedTraining && state.trainings[0]) {
      setTrainingId(state.trainings[0].id);
    }
  }, [selectedTraining, state.trainings]);

  useEffect(() => {
    if (modules.length > 0 && !modules.some((module) => module.id === activeLessonModuleId)) {
      setLessonModuleId(modules[0].id);
    }
  }, [activeLessonModuleId, modules]);

  useEffect(() => {
    if (trainingFolders.length > 0 && !trainingFolders.some((folder) => folder.id === activeMaterialFolderId)) {
      setMaterialFolderId(trainingFolders[0].id);
    }
  }, [activeMaterialFolderId, trainingFolders]);

  const totals = useMemo(
    () => ({
      trainings: state.trainings.length,
      folders: state.folders.length,
      modules: state.modules.length,
      lessons: state.lessons.length,
      materials: state.materials.length,
      homeworks: state.homeworkTemplates.length,
    }),
    [state],
  );

  if (!currentUser || currentUser.role !== "admin") {
    return (
      <AccessDeniedPanel
        title="Админка обучения"
        result={{
          allowed: false,
          reason: "login",
          message: currentUser ? "Недоступно для текущей роли" : "Нужно войти",
        }}
      />
    );
  }

  const addTraining = () => {
    if (!newTrainingTitle.trim()) {
      return;
    }
    const training: Training = {
      id: createId("training-custom"),
      title: newTrainingTitle.trim(),
      subtitle: "Новый тренинг",
      tagline: "Структуру можно собрать в админке",
      description: "Черновик тренинга. Добавьте папки, модули, уроки, материалы и доступы.",
      order: state.trainings.length + 1,
      status: "draft",
      accessPolicy: defaultPolicy(["basic", "mentor", "vip"], "Новый тренинг"),
      coverStyle: "funnel",
      folderIds: [],
      moduleIds: [],
    };
    saveEntity("trainings", training);
    setTrainingId(training.id);
    setNewTrainingTitle("");
  };

  const updateTraining = (training: Training) => saveEntity("trainings", training);

  const updateTariff = (tariff: Tariff) => saveEntity("tariffs", tariff);

  const uploadCoverFor = async (
    key: "trainings" | "folders" | "modules" | "lessons" | "lessonBlocks" | "materials",
    entity: Training | Folder | Module | Lesson | LessonBlock | Material,
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }

    const statusKey = `${key}:${entity.id}`;
    setCoverUploadState((current) => ({ ...current, [statusKey]: "Загружаем обложку..." }));

    try {
      const coverImage = await uploadCoverImage(file);
      if (key === "trainings") {
        saveEntity("trainings", { ...(entity as Training), coverImage });
      }
      if (key === "folders") {
        saveEntity("folders", { ...(entity as Folder), coverImage });
      }
      if (key === "modules") {
        saveEntity("modules", { ...(entity as Module), coverImage });
      }
      if (key === "lessons") {
        saveEntity("lessons", { ...(entity as Lesson), coverImage });
      }
      if (key === "lessonBlocks") {
        saveEntity("lessonBlocks", { ...(entity as LessonBlock), coverImage });
      }
      if (key === "materials") {
        saveEntity("materials", { ...(entity as Material), coverImage });
      }
      setCoverUploadState((current) => ({ ...current, [statusKey]: "Обложка обновлена" }));
    } catch {
      setCoverUploadState((current) => ({ ...current, [statusKey]: "Не удалось загрузить обложку" }));
    }
  };

  const coverUploadMessage = (key: string, id: string) => coverUploadState[`${key}:${id}`] || "";
  const materialUploadMessage = (id: string) => materialUploadState[id] || "";

  const handleResetState = () => {
    const confirmed = window.confirm(
      "Сброс вернет стартовую структуру курса. Перед сбросом сервер сделает резервную копию, а привязанные локальные обложки и файлы материалов будут сохранены там, где это возможно. Продолжить?",
    );
    if (confirmed) {
      resetState();
    }
  };

  const uploadFileForMaterial = async (material: Material, event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }

    setMaterialUploadState((current) => ({ ...current, [material.id]: "Загружаем файл материала..." }));

    try {
      const uploadedFile = await uploadMaterialFile(file);
      saveEntity("materials", {
        ...material,
        materialType: "file",
        url: uploadedFile.url,
        fileName: uploadedFile.name,
        fileSize: uploadedFile.size,
        metaLabel: "файл",
      });
      setMaterialUploadState((current) => ({ ...current, [material.id]: "Файл прикреплен" }));
    } catch {
      setMaterialUploadState((current) => ({ ...current, [material.id]: "Не удалось загрузить файл" }));
    }
  };

  const saveMaterialContent = (material: Material, value: string) => {
    if (material.materialType === "link" || material.materialType === "file" || material.materialType === "embed") {
      saveEntity("materials", { ...material, url: value });
      return;
    }
    saveEntity("materials", { ...material, body: value });
  };

  const addTimecode = (lesson: Lesson) => {
    const timecodes = lesson.timecodes || [];
    const timecode: LessonTimecode = {
      id: createId("timecode"),
      label: "Новый таймкод",
      seconds: timecodes.length ? Math.max(...timecodes.map((item) => item.seconds)) + 60 : 0,
      note: "",
    };
    saveEntity("lessons", { ...lesson, timecodes: [...timecodes, timecode] });
  };

  const updateTimecode = (lesson: Lesson, timecodeId: string, patch: Partial<LessonTimecode>) => {
    saveEntity("lessons", {
      ...lesson,
      timecodes: (lesson.timecodes || []).map((item) => (item.id === timecodeId ? { ...item, ...patch } : item)),
    });
  };

  const removeTimecode = (lesson: Lesson, timecodeId: string) => {
    saveEntity("lessons", {
      ...lesson,
      timecodes: (lesson.timecodes || []).filter((item) => item.id !== timecodeId),
    });
  };

  const trainingPreviewPath = (training: Training) => `/trainings/${training.id}`;
  const folderPreviewPath = (folder: Folder) =>
    folder.kind === "folder" ? `/trainings/${folder.trainingId}/folders/${folder.id}` : `/trainings/${folder.trainingId}#folder-${folder.id}`;
  const modulePreviewPath = (module: Module) => `/trainings/${module.trainingId}/modules/${module.id}`;
  const lessonPreviewPath = (lesson: Lesson) => {
    const module = state.modules.find((item) => item.id === lesson.moduleId);
    return module ? `/trainings/${module.trainingId}/modules/${module.id}/lessons/${lesson.id}` : "/trainings";
  };
  const materialPreviewPath = (material: Material) => {
    if (material.parentType === "folder") {
      return `/trainings/${selectedTraining?.id || ""}/folders/${material.parentId}#material-${material.id}`;
    }
    const lesson = state.lessons.find((item) => item.id === material.parentId);
    return lesson ? lessonPreviewPath(lesson) : "/trainings";
  };

  const addFolder = () => {
    if (!selectedTraining || !newFolderTitle.trim()) {
      return;
    }
    const parentFolderId = newFolderParentId || null;
    const folder: Folder = {
      id: createId("folder-custom"),
      trainingId: selectedTraining.id,
      parentFolderId,
      kind: newFolderKind,
      externalUrl: newFolderKind === "external" ? newFolderUrl.trim() : undefined,
      itemIds: [],
      title: newFolderTitle.trim(),
      description: newFolderKind === "external" ? "Внешний ресурс тренинга." : "Папка с материалами тренинга.",
      order: getFoldersForTraining(state, selectedTraining.id, parentFolderId).length + 1,
      status: "draft",
      accessPolicy: selectedTraining.accessPolicy,
      coverStyle: "brief",
    };
    saveEntity("folders", folder);
    updateTraining({ ...selectedTraining, folderIds: [...new Set([...selectedTraining.folderIds, folder.id])] });
    setNewFolderTitle("");
    setNewFolderUrl("");
    setNewFolderParentId("");
    setMaterialFolderId(folder.id);
  };

  const addFolderMaterial = () => {
    const folder = state.folders.find((item) => item.id === activeMaterialFolderId);
    if (!folder || !newMaterialTitle.trim()) {
      return;
    }
    const material: Material = {
      id: createId("material-custom"),
      parentType: "folder",
      parentId: folder.id,
      materialType: newMaterialType,
      title: newMaterialTitle.trim(),
      description: "Материал добавлен из админки.",
      order: getMaterialsForParent(state, "folder", folder.id).length + 1,
      status: "draft",
      accessPolicy: folder.accessPolicy,
      coverStyle: "notebook",
      body: newMaterialType === "link" ? undefined : "Замените текст материала.",
      url: newMaterialType === "link" ? "https://example.com" : undefined,
      metaLabel: materialTypeLabels[newMaterialType].toLowerCase(),
    };
    saveEntity("materials", material);
    saveEntity("folders", { ...folder, itemIds: [...new Set([...folder.itemIds, material.id])] });
    setNewMaterialTitle("");
  };

  const addModule = () => {
    if (!selectedTraining || !newModuleTitle.trim()) {
      return;
    }
    const module: Module = {
      id: createId("module-custom"),
      trainingId: selectedTraining.id,
      title: newModuleTitle.trim(),
      description: "Новый модуль, добавленный из админки прототипа.",
      order: modules.length + 1,
      status: "draft",
      accessPolicy: selectedTraining.accessPolicy,
      coverStyle: "notebook",
      lessonIds: [],
    };
    saveEntity("modules", module);
    updateTraining({ ...selectedTraining, moduleIds: [...new Set([...selectedTraining.moduleIds, module.id])] });
    setNewModuleTitle("");
    setLessonModuleId(module.id);
  };

  const addLesson = () => {
    const module = state.modules.find((item) => item.id === activeLessonModuleId);
    if (!module || !newLessonTitle.trim()) {
      return;
    }
    const lessonId = createId("lesson-custom");
    const blockId = `${lessonId}-block`;
    const materialId = `${lessonId}-material`;
    const lesson: Lesson = {
      id: lessonId,
      moduleId: module.id,
      title: newLessonTitle.trim(),
      description: "Черновик урока из админки.",
      summary: "Добавьте видео, материалы и домашку перед публикацией.",
      order: getLessonsForModule(state, module.id).length + 1,
      status: "draft",
      accessPolicy: module.accessPolicy,
      coverStyle: module.coverStyle,
      durationMinutes: 10,
      unlockDelayHours: 0,
      videoProvider: "external",
      videoUrl: "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
      kinescopeVideoId: "",
      kinescopePlayerId: "",
      kinescopeUseDrmAuth: true,
      kinescopeUseWatermark: true,
      blockIds: [blockId],
      materialIds: [materialId],
      homeworkTemplateId: null,
      timecodes: [],
    };
    const block: LessonBlock = {
      id: blockId,
      lessonId,
      type: "text",
      title: "Черновик блока",
      body: "Замените текст, видео и материалы перед публикацией.",
      bullets: [],
      order: 1,
    };
    const material: Material = {
      id: materialId,
      parentType: "lesson",
      parentId: lessonId,
      materialType: "text",
      title: "Черновик материала",
      description: "Материал можно заменить на ссылку, файл, шаблон или промпт.",
      order: 1,
      status: "draft",
      accessPolicy: lesson.accessPolicy,
      coverStyle: lesson.coverStyle,
      body: "Описание материала.",
      metaLabel: "материал урока",
    };
    saveEntity("lessons", lesson);
    saveEntity("lessonBlocks", block);
    saveEntity("materials", material);
    saveEntity("modules", { ...module, lessonIds: [...new Set([...module.lessonIds, lessonId])] });
    setNewLessonTitle("");
  };

  const addLessonBlock = (lesson: Lesson) => {
    const currentBlocks = getBlocksForLesson(state, lesson.id);
    const block: LessonBlock = {
      id: createId("lesson-block-custom"),
      lessonId: lesson.id,
      type: "text",
      title: "Новый блок",
      body: "Опишите идею, задание или подсказку для ученика.",
      bullets: [],
      order: currentBlocks.length + 1,
      status: "draft",
    };
    saveEntity("lessonBlocks", block);
    saveEntity("lessons", { ...lesson, blockIds: [...new Set([...lesson.blockIds, block.id])] });
  };

  const archiveLessonBlock = (_lesson: Lesson, block: LessonBlock) => {
    saveEntity("lessonBlocks", { ...block, status: "archived" });
  };

  const moveLesson = (lesson: Lesson, nextModuleId: string) => {
    if (lesson.moduleId === nextModuleId) {
      return;
    }
    const sourceModule = state.modules.find((module) => module.id === lesson.moduleId);
    const targetModule = state.modules.find((module) => module.id === nextModuleId);
    if (!targetModule) {
      return;
    }
    saveEntity("lessons", {
      ...lesson,
      moduleId: targetModule.id,
      order: getLessonsForModule(state, targetModule.id).length + 1,
      accessPolicy: targetModule.accessPolicy,
    });
    if (sourceModule) {
      saveEntity("modules", {
        ...sourceModule,
        lessonIds: sourceModule.lessonIds.filter((id) => id !== lesson.id),
      });
    }
    saveEntity("modules", {
      ...targetModule,
      lessonIds: [...new Set([...targetModule.lessonIds, lesson.id])],
    });
  };

  const addLessonMaterial = (lesson: Lesson) => {
    const material: Material = {
      id: createId("material-lesson"),
      parentType: "lesson",
      parentId: lesson.id,
      materialType: "text",
      title: "Новый материал урока",
      description: "Материал добавлен из админки.",
      order: getMaterialsForParent(state, "lesson", lesson.id).length + 1,
      status: "draft",
      accessPolicy: lesson.accessPolicy,
      coverStyle: lesson.coverStyle,
      body: "Замените содержимое материала.",
      metaLabel: "материал урока",
    };
    saveEntity("materials", material);
    saveEntity("lessons", { ...lesson, materialIds: [...new Set([...lesson.materialIds, material.id])] });
  };

  const upsertHomework = (lesson: Lesson) => {
    const existing = state.homeworkTemplates.find((item) => item.id === lesson.homeworkTemplateId);
    if (existing) {
      saveEntity("homeworkTemplates", existing);
      return;
    }
    const template: HomeworkTemplate = {
      id: createId("homework"),
      lessonId: lesson.id,
      title: "Домашнее задание",
      prompt: "Опишите выполненную работу и приложите ссылку или файл.",
      checklist: ["Ответ связан с уроком", "Приложен результат работы", "Есть вопросы для проверки"],
      requiredTariffIds: ["mentor", "vip"],
    };
    saveEntity("homeworkTemplates", template);
    saveEntity("lessons", { ...lesson, homeworkTemplateId: template.id });
  };

  return (
    <section className="board-section">
      <ChalkTitle
        eyebrow="контент-оператор"
        title="Админка обучения"
        text="Редактор управляет тарифами, тренингами, папками, внешними блоками, модулями, уроками, материалами, видео и домашками без правки кода."
      />

      <section className="chalk-panel admin-guide" aria-label="Быстрый маршрут по админке">
        <div className="panel-head">
          <div>
            <h2>С чего начать</h2>
            <AdminHint>Все изменения сохраняются сразу. Для показа ученикам ставь статус «опубликовано».</AdminHint>
          </div>
          {selectedTraining ? (
            <a className="chalk-button ghost" href={`/trainings/${selectedTraining.id}`} target="_blank" rel="noreferrer">
              Открыть тренинг
            </a>
          ) : null}
        </div>
        <div className="admin-guide-steps">
          {adminGuideSteps.map((step, index) => (
            <div className="admin-guide-step" key={step.title}>
              <span>{index + 1}</span>
              <strong>{step.title}</strong>
              <p>{step.text}</p>
            </div>
          ))}
        </div>
        <nav className="admin-jump-nav" aria-label="Разделы админки">
          {adminQuickLinks.map((item) => (
            <a href={item.href} key={item.href}>
              {item.label}
            </a>
          ))}
        </nav>
      </section>

      <div className="admin-stats">
        {Object.entries(totals).map(([key, value]) => (
          <div className="chalk-card compact" key={key}>
            <strong>{value}</strong>
            <span>{totalLabels[key as keyof typeof totalLabels]}</span>
          </div>
        ))}
      </div>

      <div className="admin-grid">
        <section className="chalk-panel" id="admin-tariffs">
          <h2>Тарифы</h2>
          <AdminHint>
            Платные тарифы показываются на лендинге. «Нулевой урок» нужен только для закрытого бесплатного доступа после
            опроса и на главной странице не выводится.
          </AdminHint>
          <div className="admin-list">
            {[...state.tariffs].sort((left, right) => left.sortOrder - right.sortOrder).map((tariff) => (
              <article className="admin-row tariff-admin-row" key={tariff.id}>
                <div className="admin-row-head wide-field">
                  <div>
                    <span className="chalk-eyebrow">тариф</span>
                    <strong>{tariff.title}</strong>
                  </div>
                  {tariff.id === "zero" ? <span className="mini-badge">скрыт на главной</span> : <PreviewLink to="/#tariffs">Смотреть тарифы</PreviewLink>}
                </div>
                <label>
                  Название
                  <input value={tariff.title} onChange={(event) => updateTariff({ ...tariff, title: event.target.value })} />
                </label>
                <label>
                  Цена
                  <input value={tariff.priceLabel} onChange={(event) => updateTariff({ ...tariff, priceLabel: event.target.value })} />
                </label>
                <label>
                  Порядок
                  <input
                    type="number"
                    value={tariff.sortOrder}
                    onChange={(event) => updateTariff({ ...tariff, sortOrder: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Метка
                  <input value={tariff.highlight} onChange={(event) => updateTariff({ ...tariff, highlight: event.target.value })} />
                </label>
                <label>
                  Окно доступа
                  <input value={tariff.accessWindow} onChange={(event) => updateTariff({ ...tariff, accessWindow: event.target.value })} />
                </label>
                <label>
                  Смысл тарифа
                  <textarea
                    rows={2}
                    value={tariff.tagline}
                    onChange={(event) => updateTariff({ ...tariff, tagline: event.target.value })}
                  />
                </label>
                <label className="wide-field">
                  Состав тарифа, по строкам
                  <textarea
                    rows={5}
                    value={tariff.features.join("\n")}
                    onChange={(event) => updateTariff({ ...tariff, features: parseChecklist(event.target.value) })}
                  />
                </label>
              </article>
            ))}
          </div>
        </section>

        <section className="chalk-panel" id="admin-training">
          <h2>Тренинги</h2>
          <AdminHint>Выбери тренинг, с которым работаешь. Все разделы ниже редактируют именно его.</AdminHint>
          <div className="admin-create-row training-create-row">
            <input
              value={newTrainingTitle}
              onChange={(event) => setNewTrainingTitle(event.target.value)}
              placeholder="Название нового тренинга"
            />
            <button className="chalk-button ghost" type="button" onClick={addTraining}>
              Создать тренинг
            </button>
          </div>
          <label>
            Текущий тренинг
            <select value={selectedTraining?.id || ""} onChange={(event) => setTrainingId(event.target.value)}>
              {state.trainings.map((training) => (
                <option value={training.id} key={training.id}>
                  {training.title}
                </option>
              ))}
            </select>
          </label>
          {selectedTraining ? (
            <div className="editor-card">
              <div className="admin-row-head">
                <div>
                  <span className="chalk-eyebrow">страница тренинга</span>
                  <strong>{selectedTraining.title}</strong>
                </div>
                <div className="inline-admin-actions compact-actions">
                  <PreviewLink to={trainingPreviewPath(selectedTraining)}>Смотреть тренинг</PreviewLink>
                  <ArchiveButton
                    entityLabel="Тренинг"
                    title={selectedTraining.title}
                    onConfirm={() => updateTraining({ ...selectedTraining, status: "archived" })}
                  />
                </div>
              </div>
              <EntityCover entity={selectedTraining} />
              <label className="cover-upload-field">
                Своя картинка-обложка тренинга
                <input type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.avif" onChange={(event) => void uploadCoverFor("trainings", selectedTraining, event)} />
                <FieldHelp>Можно JPG, PNG или WebP. Картинка появится на карточке и странице тренинга.</FieldHelp>
                {coverUploadMessage("trainings", selectedTraining.id) ? (
                  <small>{coverUploadMessage("trainings", selectedTraining.id)}</small>
                ) : null}
              </label>
              <div className="field-grid two">
                <label>
                  Название
                  <input
                    value={selectedTraining.title}
                    onChange={(event) => updateTraining({ ...selectedTraining, title: event.target.value })}
                  />
                </label>
                <label>
                  Статус
                  <select
                    value={selectedTraining.status}
                    onChange={(event) => updateTraining({ ...selectedTraining, status: event.target.value as PublishStatus })}
                  >
                    <option value="draft">черновик</option>
                    <option value="published">опубликовано</option>
                    <option value="archived">архив</option>
                  </select>
                  <FieldHelp>«Опубликовано» видно ученикам, «черновик» оставь для подготовки.</FieldHelp>
                </label>
                <label>
                  Подзаголовок
                  <input
                    value={selectedTraining.subtitle}
                    onChange={(event) => updateTraining({ ...selectedTraining, subtitle: event.target.value })}
                  />
                </label>
              </div>
              <label>
                Описание
                <textarea
                  rows={3}
                  value={selectedTraining.description}
                  onChange={(event) => updateTraining({ ...selectedTraining, description: event.target.value })}
                />
              </label>
              <PolicyEditor
                policy={selectedTraining.accessPolicy}
                onChange={(accessPolicy) => updateTraining({ ...selectedTraining, accessPolicy })}
              />
            </div>
          ) : null}
        </section>
      </div>

      {selectedTraining ? (
        <section className="chalk-panel" id="admin-folders">
          <div className="panel-head">
            <div>
              <h2>Папки, внешние блоки и материалы</h2>
              <AdminHint>
                Папки открываются внутри платформы. Внешний блок ведет по ссылке. Материалы лежат внутри выбранной папки.
              </AdminHint>
            </div>
            <TariffBadges tariffIds={selectedTraining.accessPolicy.tariffIds} />
          </div>
          <div className="admin-create-row folder-create-row">
            <input
              value={newFolderTitle}
              onChange={(event) => setNewFolderTitle(event.target.value)}
              placeholder="Название папки или внешнего блока"
            />
            <select value={newFolderKind} onChange={(event) => setNewFolderKind(event.target.value as FolderKind)}>
              <option value="folder">папка</option>
              <option value="external">внешний блок</option>
            </select>
            <select value={newFolderParentId} onChange={(event) => setNewFolderParentId(event.target.value)}>
              <option value="">верхний уровень</option>
              {trainingFolders.map((folder) => (
                <option value={folder.id} key={folder.id}>
                  {formatFolderOption(folder)}
                </option>
              ))}
            </select>
            <input
              value={newFolderUrl}
              onChange={(event) => setNewFolderUrl(event.target.value)}
              placeholder="Ссылка для внешнего блока"
            />
            <button className="chalk-button ghost" type="button" onClick={addFolder}>
              Добавить блок
            </button>
          </div>
          <div className="admin-create-row material-create-row">
            <select value={activeMaterialFolderId} onChange={(event) => setMaterialFolderId(event.target.value)}>
              {trainingFolders.map((folder) => (
                <option value={folder.id} key={folder.id}>
                  {formatFolderOption(folder)}
                </option>
              ))}
            </select>
            <input
              value={newMaterialTitle}
              onChange={(event) => setNewMaterialTitle(event.target.value)}
              placeholder="Название материала в папке"
            />
            <select value={newMaterialType} onChange={(event) => setNewMaterialType(event.target.value as MaterialType)}>
              {materialTypes.map((type) => (
                <option value={type} key={type}>
                  {materialTypeLabels[type]}
                </option>
              ))}
            </select>
            <button className="chalk-button ghost" type="button" onClick={addFolderMaterial}>
              Добавить материал
            </button>
          </div>

          <div className="admin-folder-grid">
            {trainingFolders.map((folder) => {
              const folderMaterials = getMaterialsForParent(state, "folder", folder.id);
              return (
                <details className="chalk-details" key={folder.id}>
                  <summary>
                    <span>{folder.kind === "external" ? "внешний" : "папка"}</span>
                    <strong>{folder.title}</strong>
                    <small>{statusLabels[folder.status]} · {folderMaterials.length} материалов</small>
                  </summary>
                  <div className="admin-module-editor folder-editor">
                    <div className="admin-row-head wide-field">
                      <div>
                        <span className="chalk-eyebrow">{folder.kind === "external" ? "внешний блок" : "папка"}</span>
                        <strong>{folder.title}</strong>
                      </div>
                      <div className="inline-admin-actions compact-actions">
                        <PreviewLink to={folderPreviewPath(folder)}>
                          {folder.kind === "external" ? "Смотреть карточку" : "Смотреть папку"}
                        </PreviewLink>
                        {folder.kind === "external" && folder.externalUrl ? (
                          <a className="chalk-button ghost" href={folder.externalUrl} target="_blank" rel="noreferrer">
                            Открыть ссылку
                          </a>
                        ) : null}
                        <ArchiveButton
                          entityLabel={folder.kind === "external" ? "Внешний блок" : "Папку"}
                          title={folder.title}
                          onConfirm={() => archiveEntity("folders", folder.id)}
                        />
                      </div>
                    </div>
                    <label>
                      Название
                      <input
                        value={folder.title}
                        onChange={(event) => saveEntity("folders", { ...folder, title: event.target.value })}
                      />
                    </label>
                    <label>
                      Статус
                      <select
                        value={folder.status}
                        onChange={(event) => saveEntity("folders", { ...folder, status: event.target.value as PublishStatus })}
                      >
                        <option value="draft">черновик</option>
                        <option value="published">опубликовано</option>
                        <option value="archived">архив</option>
                      </select>
                      <FieldHelp>Архив скрывает папку из списка, но не удаляет ее из данных.</FieldHelp>
                    </label>
                    <label>
                      Родитель
                      <select
                        value={folder.parentFolderId || ""}
                        onChange={(event) => saveEntity("folders", { ...folder, parentFolderId: event.target.value || null })}
                      >
                        <option value="">верхний уровень</option>
                        {trainingFolders
                          .filter((item) => item.id !== folder.id)
                          .map((item) => (
                            <option value={item.id} key={item.id}>
                              {formatFolderOption(item)}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      Порядок
                      <input
                        type="number"
                        value={folder.order}
                        onChange={(event) => saveEntity("folders", { ...folder, order: Number(event.target.value) })}
                      />
                    </label>
                    <label>
                      Ссылка
                      <input
                        value={folder.externalUrl || ""}
                        placeholder="https://..."
                        onChange={(event) => saveEntity("folders", { ...folder, externalUrl: event.target.value })}
                      />
                      <FieldHelp>Заполняй только для внешнего блока.</FieldHelp>
                    </label>
                    <label className="cover-upload-field">
                      Своя картинка-обложка
                      <input type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.avif" onChange={(event) => void uploadCoverFor("folders", folder, event)} />
                      <FieldHelp>Эта картинка будет на карточке папки или внешнего блока.</FieldHelp>
                      {coverUploadMessage("folders", folder.id) ? <small>{coverUploadMessage("folders", folder.id)}</small> : null}
                    </label>
                  </div>
                  <PolicyEditor
                    compact
                    policy={folder.accessPolicy}
                    onChange={(accessPolicy) => saveEntity("folders", { ...folder, accessPolicy })}
                  />
                  <div className="material-editor-list">
                    {folderMaterials.map((material) => (
                      <article className="admin-row material-admin-row" key={material.id}>
                        <input
                          value={material.title}
                          placeholder="Название материала"
                          onChange={(event) => saveEntity("materials", { ...material, title: event.target.value })}
                        />
                        <select
                          value={material.materialType}
                          onChange={(event) => saveEntity("materials", { ...material, materialType: event.target.value as MaterialType })}
                        >
                          {materialTypes.map((type) => (
                            <option value={type} key={type}>
                              {materialTypeLabels[type]}
                            </option>
                          ))}
                        </select>
                        <select
                          value={material.status}
                          onChange={(event) => saveEntity("materials", { ...material, status: event.target.value as PublishStatus })}
                        >
                          <option value="draft">черновик</option>
                          <option value="published">опубликовано</option>
                          <option value="archived">архив</option>
                        </select>
                        <label className="cover-upload-field compact-upload-field">
                          Своя картинка
                          <input type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.avif" onChange={(event) => void uploadCoverFor("materials", material, event)} />
                          <FieldHelp>Картинка для карточки материала.</FieldHelp>
                          {coverUploadMessage("materials", material.id) ? <small>{coverUploadMessage("materials", material.id)}</small> : null}
                        </label>
                        <div className="inline-admin-actions compact-actions">
                          <PreviewLink to={materialPreviewPath(material)}>Смотреть</PreviewLink>
                          <ArchiveButton
                            entityLabel="Материал"
                            title={material.title}
                            onConfirm={() => archiveEntity("materials", material.id)}
                          />
                        </div>
                        <textarea
                          rows={2}
                          placeholder={materialContentPlaceholder(material)}
                          value={materialContentValue(material)}
                          onChange={(event) => saveMaterialContent(material, event.target.value)}
                        />
                        <label className="material-file-upload wide-field">
                          Файл для скачивания
                          <input type="file" accept=".pdf,.txt,.md,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.png,.jpg,.jpeg,.webp,.gif,.mp4,.mov,.m4v,.webm" onChange={(event) => void uploadFileForMaterial(material, event)} />
                          <FieldHelp>
                            Если загрузить файл, тип материала станет «Файл», а ссылка будет защищена доступом к папке.
                          </FieldHelp>
                          {material.fileName ? (
                            <small>
                              Прикреплен: {material.fileName}
                              {formatFileSize(material.fileSize) ? ` · ${formatFileSize(material.fileSize)}` : ""}
                            </small>
                          ) : null}
                          {materialUploadMessage(material.id) ? <small>{materialUploadMessage(material.id)}</small> : null}
                        </label>
                      </article>
                    ))}
                  </div>
                </details>
              );
            })}
          </div>
        </section>
      ) : null}

      {selectedTraining ? (
        <section className="chalk-panel" id="admin-program">
          <div className="panel-head">
            <div>
              <h2>Модули, уроки, видео и домашки</h2>
              <AdminHint>
                Модуль — глава курса. Урок — видео и страница занятия. Блоки урока — карточки с текстом, чеклистом или действием.
              </AdminHint>
            </div>
            <TariffBadges tariffIds={selectedTraining.accessPolicy.tariffIds} />
          </div>

          <div className="admin-create-row module-create-row">
            <input
              value={newModuleTitle}
              onChange={(event) => setNewModuleTitle(event.target.value)}
              placeholder="Название нового модуля"
            />
            <button className="chalk-button ghost" type="button" onClick={addModule}>
              Добавить модуль
            </button>
            <select value={activeLessonModuleId} onChange={(event) => setLessonModuleId(event.target.value)}>
              {modules.map((module) => (
                <option value={module.id} key={module.id}>
                  Модуль {module.order}
                </option>
              ))}
            </select>
            <input
              value={newLessonTitle}
              onChange={(event) => setNewLessonTitle(event.target.value)}
              placeholder="Название нового урока"
            />
            <button className="chalk-button ghost" type="button" onClick={addLesson}>
              Добавить урок
            </button>
          </div>

          <div className="program-list admin-program">
            {modules.map((module) => {
              const moduleLessons = getLessonsForModule(state, module.id);
              return (
              <details className="chalk-details" key={module.id}>
                <summary>
                  <span>Модуль {module.order}</span>
                  <strong>{module.title}</strong>
                  <small>{statusLabels[module.status]} · {moduleLessons.length} уроков</small>
                </summary>
                <div className="admin-module-editor">
                  <div className="admin-row-head wide-field">
                    <div>
                      <span className="chalk-eyebrow">модуль курса</span>
                      <strong>{module.title}</strong>
                    </div>
                    <div className="inline-admin-actions compact-actions">
                      <PreviewLink to={modulePreviewPath(module)}>Смотреть модуль</PreviewLink>
                      <ArchiveButton
                        entityLabel="Модуль"
                        title={module.title}
                        onConfirm={() => saveEntity("modules", { ...module, status: "archived" })}
                      />
                    </div>
                  </div>
                  <label>
                    Название
                    <input
                      value={module.title}
                      onChange={(event) => saveEntity("modules", { ...module, title: event.target.value })}
                    />
                  </label>
                  <label>
                    Статус
                    <select
                      value={module.status}
                      onChange={(event) => saveEntity("modules", { ...module, status: event.target.value as PublishStatus })}
                    >
                      <option value="draft">черновик</option>
                      <option value="published">опубликовано</option>
                      <option value="archived">архив</option>
                    </select>
                  </label>
                  <label>
                    Порядок
                    <input
                      type="number"
                      value={module.order}
                      onChange={(event) => saveEntity("modules", { ...module, order: Number(event.target.value) })}
                    />
                  </label>
                  <label className="cover-upload-field">
                    Своя картинка-обложка
                    <input type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.avif" onChange={(event) => void uploadCoverFor("modules", module, event)} />
                    <FieldHelp>Картинка на карточке модуля в программе тренинга.</FieldHelp>
                    {coverUploadMessage("modules", module.id) ? <small>{coverUploadMessage("modules", module.id)}</small> : null}
                  </label>
                </div>
                <PolicyEditor
                  compact
                  policy={module.accessPolicy}
                  onChange={(accessPolicy) => saveEntity("modules", { ...module, accessPolicy })}
                />
                <div className="admin-lessons lesson-picker-list">
                  <div className="lesson-picker-head">
                    <strong>Уроки модуля</strong>
                    <span>Открой только тот урок, который хочешь редактировать.</span>
                  </div>
                  {moduleLessons.length === 0 ? <p className="text-muted">В этом модуле пока нет уроков.</p> : null}
                  {moduleLessons.map((lesson) => {
                    const template = state.homeworkTemplates.find((item) => item.id === lesson.homeworkTemplateId);
                    const lessonMaterials = getMaterialsForParent(state, "lesson", lesson.id);
                    const lessonBlocks = getBlocksForLesson(state, lesson.id);
                    return (
                      <details className="lesson-edit-details" key={lesson.id}>
                        <summary className="lesson-edit-summary">
                          <span>Урок {lesson.order}</span>
                          <strong>{lesson.title}</strong>
                          <small>{statusLabels[lesson.status]} · {lesson.durationMinutes} мин</small>
                        </summary>
                        <article className="admin-row lesson-admin-row">
                        <div className="admin-row-head wide-field">
                          <div>
                            <span className="chalk-eyebrow">страница урока</span>
                            <strong>{lesson.title}</strong>
                          </div>
                          <div className="inline-admin-actions compact-actions">
                            <PreviewLink to={lessonPreviewPath(lesson)}>Смотреть урок</PreviewLink>
                            <ArchiveButton
                              entityLabel="Урок"
                              title={lesson.title}
                              onConfirm={() => saveEntity("lessons", { ...lesson, status: "archived" })}
                            />
                          </div>
                        </div>
                        <label>
                          Название
                          <input
                            value={lesson.title}
                            onChange={(event) => saveEntity("lessons", { ...lesson, title: event.target.value })}
                          />
                        </label>
                        <label>
                          Статус
                          <select
                            value={lesson.status}
                            onChange={(event) => saveEntity("lessons", { ...lesson, status: event.target.value as PublishStatus })}
                          >
                            <option value="draft">черновик</option>
                            <option value="published">опубликовано</option>
                            <option value="archived">архив</option>
                          </select>
                        </label>
                        <label>
                          Модуль
                          <select value={lesson.moduleId} onChange={(event) => moveLesson(lesson, event.target.value)}>
                            {modules.map((targetModule) => (
                              <option value={targetModule.id} key={targetModule.id}>
                                {targetModule.title}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Порядок
                          <input
                            type="number"
                            value={lesson.order}
                            onChange={(event) => saveEntity("lessons", { ...lesson, order: Number(event.target.value) })}
                          />
                        </label>
                        <label>
                          Длительность, мин
                          <input
                            type="number"
                            value={lesson.durationMinutes}
                            onChange={(event) => saveEntity("lessons", { ...lesson, durationMinutes: Number(event.target.value) })}
                          />
                        </label>
                        <label>
                          Открыть через, часов
                          <input
                            type="number"
                            min="0"
                            step="0.5"
                            value={lesson.unlockDelayHours ?? 0}
                            onChange={(event) =>
                              saveEntity("lessons", {
                                ...lesson,
                                unlockDelayHours: Math.max(0, Number(event.target.value) || 0),
                              })
                            }
                          />
                          <FieldHelp>
                            Первый урок считает время от создания аккаунта ученика. Каждый следующий — от планового открытия предыдущего урока.
                          </FieldHelp>
                        </label>
                        <label>
                          Где лежит видео
                          <select
                            value={lesson.videoProvider || "external"}
                            onChange={(event) => saveEntity("lessons", { ...lesson, videoProvider: event.target.value as VideoProvider })}
                          >
                            {Object.entries(videoProviderLabels).map(([value, label]) => (
                              <option value={value} key={value}>
                                {label}
                              </option>
                            ))}
                          </select>
                          <FieldHelp>Kinescope — боевой режим с проверкой доступа через backend. Прямая ссылка — только для демо или тестов.</FieldHelp>
                        </label>
                        {(lesson.videoProvider || "external") === "kinescope" ? (
                          <div className="field-grid two wide-field video-provider-box">
                            <label>
                              ID видео в Kinescope
                              <input
                                value={lesson.kinescopeVideoId || ""}
                                placeholder="Например: 2030abcd-..."
                                onChange={(event) => saveEntity("lessons", { ...lesson, kinescopeVideoId: event.target.value.trim() })}
                              />
                              <FieldHelp>Это ID загруженного видео. Прямую ссылку ученику платформа не показывает.</FieldHelp>
                            </label>
                            <label>
                              ID плеера Kinescope
                              <input
                                value={lesson.kinescopePlayerId || ""}
                                placeholder="Необязательно"
                                onChange={(event) => saveEntity("lessons", { ...lesson, kinescopePlayerId: event.target.value.trim() })}
                              />
                              <FieldHelp>Заполняй, если в Kinescope создан отдельный брендированный плеер.</FieldHelp>
                            </label>
                            <label className="checkbox-single">
                              <input
                                type="checkbox"
                                checked={lesson.kinescopeUseDrmAuth !== false}
                                onChange={(event) => saveEntity("lessons", { ...lesson, kinescopeUseDrmAuth: event.target.checked })}
                              />
                              Включить авторизационный backend Kinescope
                            </label>
                            <label className="checkbox-single">
                              <input
                                type="checkbox"
                                checked={lesson.kinescopeUseWatermark !== false}
                                onChange={(event) => saveEntity("lessons", { ...lesson, kinescopeUseWatermark: event.target.checked })}
                              />
                              Добавлять персональный водяной знак
                            </label>
                          </div>
                        ) : (
                          <label className="wide-field">
                            Прямая ссылка на видео
                            <input
                              value={lesson.videoUrl}
                              placeholder="https://..."
                              onChange={(event) => saveEntity("lessons", { ...lesson, videoUrl: event.target.value })}
                            />
                            <FieldHelp>Оставь для локального демо. Для платных уроков лучше выбрать Kinescope.</FieldHelp>
                          </label>
                        )}
                        <label className="wide-field">
                          Краткое описание
                          <textarea
                            rows={2}
                            value={lesson.summary}
                            onChange={(event) => saveEntity("lessons", { ...lesson, summary: event.target.value })}
                          />
                        </label>
                        <label className="wide-field cover-upload-field">
                          Своя картинка-обложка урока
                          <input type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.avif" onChange={(event) => void uploadCoverFor("lessons", lesson, event)} />
                          <FieldHelp>Картинка на карточке урока внутри модуля.</FieldHelp>
                          {coverUploadMessage("lessons", lesson.id) ? <small>{coverUploadMessage("lessons", lesson.id)}</small> : null}
                        </label>
                        <PolicyEditor
                          compact
                          policy={lesson.accessPolicy}
                          onChange={(accessPolicy) => saveEntity("lessons", { ...lesson, accessPolicy })}
                        />

                        <div className="timecode-editor wide-field">
                          <div className="inline-admin-actions">
                            <div>
                              <strong>Таймкоды</strong>
                              <FieldHelp>Добавляй моменты в формате 1:23 или 1:02:03. У ученика они появятся под видео.</FieldHelp>
                            </div>
                            <button className="chalk-button ghost" type="button" onClick={() => addTimecode(lesson)}>
                              Добавить таймкод
                            </button>
                          </div>
                          {(lesson.timecodes || []).length ? (
                            [...(lesson.timecodes || [])]
                              .sort((left, right) => left.seconds - right.seconds)
                              .map((timecode) => (
                                <div className="timecode-admin-row" key={timecode.id}>
                                  <label>
                                    Время
                                    <input
                                      value={formatTimeInput(timecode.seconds)}
                                      placeholder="1:23"
                                      onChange={(event) =>
                                        updateTimecode(lesson, timecode.id, { seconds: parseTimeInput(event.target.value) })
                                      }
                                    />
                                  </label>
                                  <label>
                                    Название
                                    <input
                                      value={timecode.label}
                                      placeholder="Что происходит в этом месте"
                                      onChange={(event) => updateTimecode(lesson, timecode.id, { label: event.target.value })}
                                    />
                                  </label>
                                  <label>
                                    Комментарий
                                    <input
                                      value={timecode.note || ""}
                                      placeholder="Необязательно"
                                      onChange={(event) => updateTimecode(lesson, timecode.id, { note: event.target.value })}
                                    />
                                  </label>
                                  <button
                                    className="chalk-button ghost"
                                    type="button"
                                    onClick={() => removeTimecode(lesson, timecode.id)}
                                  >
                                    Удалить
                                  </button>
                                </div>
                              ))
                          ) : (
                            <p className="text-muted">Таймкоды пока не добавлены.</p>
                          )}
                        </div>

                        <div className="lesson-block-editor">
                          <div className="inline-admin-actions">
                            <strong>Блоки урока</strong>
                            <button className="chalk-button ghost" type="button" onClick={() => addLessonBlock(lesson)}>
                              Добавить блок
                            </button>
                          </div>
                          {lessonBlocks.map((block) => (
                            <div className="lesson-block-admin-row" key={block.id}>
                              <div className="lesson-block-avatar">
                                {block.coverImage ? <img src={block.coverImage} alt="" /> : <span>{lessonBlockTypeLabels[block.type]}</span>}
                              </div>
                              <input
                                value={block.title}
                                placeholder="Название блока"
                                onChange={(event) => saveEntity("lessonBlocks", { ...block, title: event.target.value })}
                              />
                              <select
                                value={block.type}
                                onChange={(event) => saveEntity("lessonBlocks", { ...block, type: event.target.value as LessonBlockType })}
                              >
                                {lessonBlockTypes.map((type) => (
                                  <option value={type} key={type}>
                                    {lessonBlockTypeLabels[type]}
                                  </option>
                                ))}
                              </select>
                              <input
                                type="number"
                                value={block.order}
                                onChange={(event) => saveEntity("lessonBlocks", { ...block, order: Number(event.target.value) })}
                              />
                              <label className="cover-upload-field compact-upload-field">
                                Аватарка
                                <input type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.avif" onChange={(event) => void uploadCoverFor("lessonBlocks", block, event)} />
                                <FieldHelp>Маленькая картинка внутри карточки блока урока.</FieldHelp>
                                {coverUploadMessage("lessonBlocks", block.id) ? <small>{coverUploadMessage("lessonBlocks", block.id)}</small> : null}
                              </label>
                              <textarea
                                rows={2}
                                placeholder="Основной текст блока"
                                value={block.body}
                                onChange={(event) => saveEntity("lessonBlocks", { ...block, body: event.target.value })}
                              />
                              <textarea
                                rows={2}
                                value={block.bullets.join("\n")}
                                onChange={(event) => saveEntity("lessonBlocks", { ...block, bullets: parseChecklist(event.target.value) })}
                                placeholder="Пункты блока, по строкам"
                              />
                              <ArchiveButton
                                entityLabel="Блок урока"
                                title={block.title}
                                onConfirm={() => archiveLessonBlock(lesson, block)}
                              />
                            </div>
                          ))}
                        </div>

                        <div className="lesson-material-editor">
                          <div className="inline-admin-actions">
                            <strong>Материалы урока</strong>
                            <button className="chalk-button ghost" type="button" onClick={() => addLessonMaterial(lesson)}>
                              Добавить материал
                            </button>
                          </div>
                          {lessonMaterials.map((material) => (
                            <div className="lesson-material-row" key={material.id}>
                              <input
                                value={material.title}
                                placeholder="Название материала"
                                onChange={(event) => saveEntity("materials", { ...material, title: event.target.value })}
                              />
                              <select
                                value={material.materialType}
                                onChange={(event) => saveEntity("materials", { ...material, materialType: event.target.value as MaterialType })}
                              >
                                {materialTypes.map((type) => (
                                  <option value={type} key={type}>
                                    {materialTypeLabels[type]}
                                  </option>
                                ))}
                              </select>
                              <label className="cover-upload-field compact-upload-field">
                                Своя картинка
                                <input type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.avif" onChange={(event) => void uploadCoverFor("materials", material, event)} />
                                <FieldHelp>Картинка для карточки материала урока.</FieldHelp>
                                {coverUploadMessage("materials", material.id) ? <small>{coverUploadMessage("materials", material.id)}</small> : null}
                              </label>
                              <div className="inline-admin-actions compact-actions">
                                <PreviewLink to={materialPreviewPath(material)}>Смотреть</PreviewLink>
                                <ArchiveButton
                                  entityLabel="Материал"
                                  title={material.title}
                                  onConfirm={() => archiveEntity("materials", material.id)}
                                />
                              </div>
                              <textarea
                                rows={2}
                                placeholder={materialContentPlaceholder(material)}
                                value={materialContentValue(material)}
                                onChange={(event) => saveMaterialContent(material, event.target.value)}
                              />
                              <label className="material-file-upload">
                                Файл для скачивания
                                <input type="file" accept=".pdf,.txt,.md,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.png,.jpg,.jpeg,.webp,.gif,.mp4,.mov,.m4v,.webm" onChange={(event) => void uploadFileForMaterial(material, event)} />
                                <FieldHelp>
                                  Загруженный файл будет показываться ученику в материалах урока и скачиваться по защищенной ссылке.
                                </FieldHelp>
                                {material.fileName ? (
                                  <small>
                                    Прикреплен: {material.fileName}
                                    {formatFileSize(material.fileSize) ? ` · ${formatFileSize(material.fileSize)}` : ""}
                                  </small>
                                ) : null}
                                {materialUploadMessage(material.id) ? <small>{materialUploadMessage(material.id)}</small> : null}
                              </label>
                            </div>
                          ))}
                        </div>

                        <div className="homework-editor">
                          <div className="inline-admin-actions">
                            <strong>Домашка</strong>
                            <button className="chalk-button ghost" type="button" onClick={() => upsertHomework(lesson)}>
                              {template ? "Обновить шаблон" : "Добавить домашку"}
                            </button>
                            {template ? (
                              <ArchiveButton
                                entityLabel="Домашку"
                                title={template.title}
                                onConfirm={() => saveEntity("lessons", { ...lesson, homeworkTemplateId: null })}
                                description="Домашка отключится от этого урока и перестанет показываться ученикам."
                              >
                                Удалить домашку
                              </ArchiveButton>
                            ) : null}
                          </div>
                          {template ? (
                            <div className="field-grid two">
                              <label>
                                Заголовок
                                <input
                                  value={template.title}
                                  onChange={(event) => saveEntity("homeworkTemplates", { ...template, title: event.target.value })}
                                />
                              </label>
                              <label>
                                Тарифы проверки
                                <select
                                  value={template.requiredTariffIds.join(",")}
                                  onChange={(event) =>
                                    saveEntity("homeworkTemplates", {
                                      ...template,
                                      requiredTariffIds: event.target.value.split(",").filter(Boolean) as TariffId[],
                                    })
                                  }
                                >
                                  {homeworkTariffOptions.map((option) => (
                                    <option value={option.value} key={option.value}>
                                      {option.label}
                                    </option>
                                  ))}
                                </select>
                              </label>
                              <label className="wide-field">
                                Текст задания
                                <textarea
                                  rows={2}
                                  value={template.prompt}
                                  onChange={(event) => saveEntity("homeworkTemplates", { ...template, prompt: event.target.value })}
                                />
                              </label>
                              <label className="wide-field">
                                Чеклист, по строкам
                                <textarea
                                  rows={3}
                                  value={template.checklist.join("\n")}
                                  onChange={(event) =>
                                    saveEntity("homeworkTemplates", { ...template, checklist: parseChecklist(event.target.value) })
                                  }
                                />
                              </label>
                            </div>
                          ) : (
                            <p className="text-muted">Домашнее задание не подключено.</p>
                          )}
                        </div>
                        </article>
                      </details>
                    );
                  })}
                </div>
              </details>
              );
            })}
          </div>
        </section>
      ) : null}

      <div className="action-row admin-reset-row" id="admin-reset">
        <button className="chalk-button ghost" type="button" onClick={handleResetState}>
          Сбросить демо-данные
        </button>
        <AdminHint>
          Перед сбросом создается резервная копия. Локальные обложки и файлы материалов сохраняются, если элемент с тем же ID
          остается в стартовой структуре.
        </AdminHint>
      </div>
    </section>
  );
}
