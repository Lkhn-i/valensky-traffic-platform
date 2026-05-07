import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { useApp } from "../app/context";
import { AccessDeniedPanel, ChalkTitle, EntityCover, TariffBadges } from "../components/ui";
import {
  createId,
  getBlocksForLesson,
  getFoldersForTraining,
  getLessonsForModule,
  getMaterialsForParent,
  getModulesForTraining,
  refreshCover,
} from "../domain/helpers";
import type {
  AccessPolicy,
  Folder,
  FolderKind,
  HomeworkTemplate,
  Lesson,
  LessonBlock,
  LessonBlockType,
  Material,
  MaterialType,
  Module,
  PublishStatus,
  Tariff,
  TariffId,
  Training,
} from "../domain/types";

const tariffIds: TariffId[] = ["workshop", "basic", "mentor", "vip"];
const coverStyles = ["funnel", "ladder", "radar", "network", "squares", "constellation", "brief", "notebook"];
const materialTypes: MaterialType[] = ["text", "template", "prompt", "link", "file", "embed"];
const lessonBlockTypes: LessonBlockType[] = ["text", "checklist", "quote", "cta"];

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

function formatFolderOption(folder: Folder) {
  return `${folder.parentFolderId ? "↳ " : ""}${folder.title}`;
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
      <div className="checkbox-line">
        {tariffIds.map((tariffId) => (
          <label key={tariffId}>
            <input
              type="checkbox"
              checked={policy.tariffIds.includes(tariffId)}
              onChange={() => onChange(toggleTariff(policy, tariffId))}
            />
            {tariffId}
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
      <label className="checkbox-single">
        <input
          type="checkbox"
          checked={policy.sequential}
          onChange={(event) => onChange({ ...policy, sequential: event.target.checked })}
        />
        Открывать последовательно
      </label>
    </div>
  );
}

export function AdminPage() {
  const { state, currentUser, saveEntity, archiveEntity, resetState, uploadCoverImage } = useApp();
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
        backTo="/trainings"
      />
    );
  }

  const addTraining = () => {
    if (!newTrainingTitle.trim()) {
      return;
    }
    const training: Training = refreshCover({
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
    });
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

  const addFolder = () => {
    if (!selectedTraining || !newFolderTitle.trim()) {
      return;
    }
    const parentFolderId = newFolderParentId || null;
    const folder: Folder = refreshCover({
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
    });
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
    const material: Material = refreshCover({
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
      metaLabel: newMaterialType,
    });
    saveEntity("materials", material);
    saveEntity("folders", { ...folder, itemIds: [...new Set([...folder.itemIds, material.id])] });
    setNewMaterialTitle("");
  };

  const addModule = () => {
    if (!selectedTraining || !newModuleTitle.trim()) {
      return;
    }
    const module: Module = refreshCover({
      id: createId("module-custom"),
      trainingId: selectedTraining.id,
      title: newModuleTitle.trim(),
      description: "Новый модуль, добавленный из админки прототипа.",
      order: modules.length + 1,
      status: "draft",
      accessPolicy: selectedTraining.accessPolicy,
      coverStyle: "notebook",
      lessonIds: [],
    });
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
    const lesson: Lesson = refreshCover({
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
      videoUrl: "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
      blockIds: [blockId],
      materialIds: [materialId],
      homeworkTemplateId: null,
    });
    const block: LessonBlock = {
      id: blockId,
      lessonId,
      type: "text",
      title: "Черновик блока",
      body: "Замените текст, видео и материалы перед публикацией.",
      bullets: [],
      order: 1,
    };
    const material: Material = refreshCover({
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
    });
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

  const archiveLessonBlock = (lesson: Lesson, block: LessonBlock) => {
    saveEntity("lessonBlocks", { ...block, status: "archived" });
    saveEntity("lessons", { ...lesson, blockIds: lesson.blockIds.filter((id) => id !== block.id) });
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
    const material: Material = refreshCover({
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
    });
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

      <div className="admin-stats">
        {Object.entries(totals).map(([key, value]) => (
          <div className="chalk-card compact" key={key}>
            <strong>{value}</strong>
            <span>{key}</span>
          </div>
        ))}
      </div>

      <div className="admin-grid">
        <section className="chalk-panel">
          <h2>Тарифы</h2>
          <div className="admin-list">
            {[...state.tariffs].sort((left, right) => left.sortOrder - right.sortOrder).map((tariff) => (
              <article className="admin-row tariff-admin-row" key={tariff.id}>
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

        <section className="chalk-panel">
          <h2>Тренинги</h2>
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
              <EntityCover entity={selectedTraining} />
              <label className="cover-upload-field">
                Загрузить обложку тренинга
                <input type="file" accept="image/*" onChange={(event) => void uploadCoverFor("trainings", selectedTraining, event)} />
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
                </label>
                <label>
                  Подзаголовок
                  <input
                    value={selectedTraining.subtitle}
                    onChange={(event) => updateTraining({ ...selectedTraining, subtitle: event.target.value })}
                  />
                </label>
                <label>
                  Обложка
                  <select
                    value={selectedTraining.coverStyle}
                    onChange={(event) => updateTraining(refreshCover({ ...selectedTraining, coverStyle: event.target.value }))}
                  >
                    {coverStyles.map((style) => (
                      <option value={style} key={style}>
                        {style}
                      </option>
                    ))}
                  </select>
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
        <section className="chalk-panel">
          <div className="panel-head">
            <h2>Папки, внешние блоки и материалы</h2>
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
              placeholder="URL для внешнего блока"
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
                  {type}
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
                  </summary>
                  <div className="admin-module-editor folder-editor">
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
                      URL
                      <input
                        value={folder.externalUrl || ""}
                        onChange={(event) => saveEntity("folders", { ...folder, externalUrl: event.target.value })}
                      />
                    </label>
                    <label className="cover-upload-field">
                      Обложка
                      <input type="file" accept="image/*" onChange={(event) => void uploadCoverFor("folders", folder, event)} />
                      {coverUploadMessage("folders", folder.id) ? <small>{coverUploadMessage("folders", folder.id)}</small> : null}
                    </label>
                    <button className="chalk-button ghost" type="button" onClick={() => archiveEntity("folders", folder.id)}>
                      В архив
                    </button>
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
                          onChange={(event) => saveEntity("materials", { ...material, title: event.target.value })}
                        />
                        <select
                          value={material.materialType}
                          onChange={(event) => saveEntity("materials", { ...material, materialType: event.target.value as MaterialType })}
                        >
                          {materialTypes.map((type) => (
                            <option value={type} key={type}>
                              {type}
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
                          Обложка
                          <input type="file" accept="image/*" onChange={(event) => void uploadCoverFor("materials", material, event)} />
                          {coverUploadMessage("materials", material.id) ? <small>{coverUploadMessage("materials", material.id)}</small> : null}
                        </label>
                        <button className="chalk-button ghost" type="button" onClick={() => archiveEntity("materials", material.id)}>
                          В архив
                        </button>
                        <textarea
                          rows={2}
                          value={material.url || material.body || ""}
                          onChange={(event) =>
                            saveEntity(
                              "materials",
                              material.materialType === "link" || material.materialType === "file" || material.materialType === "embed"
                                ? { ...material, url: event.target.value }
                                : { ...material, body: event.target.value },
                            )
                          }
                        />
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
        <section className="chalk-panel">
          <div className="panel-head">
            <h2>Модули, уроки, видео и домашки</h2>
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
            {modules.map((module) => (
              <details className="chalk-details" key={module.id}>
                <summary>
                  <span>Модуль {module.order}</span>
                  <strong>{module.title}</strong>
                </summary>
                <div className="admin-module-editor">
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
                    Обложка
                    <select
                      value={module.coverStyle}
                      onChange={(event) => saveEntity("modules", refreshCover({ ...module, coverStyle: event.target.value }))}
                    >
                      {coverStyles.map((style) => (
                        <option value={style} key={style}>
                          {style}
                        </option>
                      ))}
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
                    Загрузить обложку
                    <input type="file" accept="image/*" onChange={(event) => void uploadCoverFor("modules", module, event)} />
                    {coverUploadMessage("modules", module.id) ? <small>{coverUploadMessage("modules", module.id)}</small> : null}
                  </label>
                </div>
                <PolicyEditor
                  compact
                  policy={module.accessPolicy}
                  onChange={(accessPolicy) => saveEntity("modules", { ...module, accessPolicy })}
                />
                <div className="admin-lessons">
                  {getLessonsForModule(state, module.id).map((lesson) => {
                    const template = state.homeworkTemplates.find((item) => item.id === lesson.homeworkTemplateId);
                    const lessonMaterials = getMaterialsForParent(state, "lesson", lesson.id);
                    const lessonBlocks = getBlocksForLesson(state, lesson.id);
                    return (
                      <article className="admin-row lesson-admin-row" key={lesson.id}>
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
                          Видео URL
                          <input value={lesson.videoUrl} onChange={(event) => saveEntity("lessons", { ...lesson, videoUrl: event.target.value })} />
                        </label>
                        <label className="wide-field">
                          Краткое описание
                          <textarea
                            rows={2}
                            value={lesson.summary}
                            onChange={(event) => saveEntity("lessons", { ...lesson, summary: event.target.value })}
                          />
                        </label>
                        <label className="wide-field cover-upload-field">
                          Загрузить обложку урока
                          <input type="file" accept="image/*" onChange={(event) => void uploadCoverFor("lessons", lesson, event)} />
                          {coverUploadMessage("lessons", lesson.id) ? <small>{coverUploadMessage("lessons", lesson.id)}</small> : null}
                        </label>
                        <PolicyEditor
                          compact
                          policy={lesson.accessPolicy}
                          onChange={(accessPolicy) => saveEntity("lessons", { ...lesson, accessPolicy })}
                        />

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
                                {block.coverImage ? <img src={block.coverImage} alt="" /> : <span>{block.type}</span>}
                              </div>
                              <input
                                value={block.title}
                                onChange={(event) => saveEntity("lessonBlocks", { ...block, title: event.target.value })}
                              />
                              <select
                                value={block.type}
                                onChange={(event) => saveEntity("lessonBlocks", { ...block, type: event.target.value as LessonBlockType })}
                              >
                                {lessonBlockTypes.map((type) => (
                                  <option value={type} key={type}>
                                    {type}
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
                                <input type="file" accept="image/*" onChange={(event) => void uploadCoverFor("lessonBlocks", block, event)} />
                                {coverUploadMessage("lessonBlocks", block.id) ? <small>{coverUploadMessage("lessonBlocks", block.id)}</small> : null}
                              </label>
                              <textarea
                                rows={2}
                                value={block.body}
                                onChange={(event) => saveEntity("lessonBlocks", { ...block, body: event.target.value })}
                              />
                              <textarea
                                rows={2}
                                value={block.bullets.join("\n")}
                                onChange={(event) => saveEntity("lessonBlocks", { ...block, bullets: parseChecklist(event.target.value) })}
                                placeholder="Пункты блока, по строкам"
                              />
                              <button className="chalk-button ghost" type="button" onClick={() => archiveLessonBlock(lesson, block)}>
                                В архив
                              </button>
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
                                onChange={(event) => saveEntity("materials", { ...material, title: event.target.value })}
                              />
                              <select
                                value={material.materialType}
                                onChange={(event) => saveEntity("materials", { ...material, materialType: event.target.value as MaterialType })}
                              >
                                {materialTypes.map((type) => (
                                  <option value={type} key={type}>
                                    {type}
                                  </option>
                                ))}
                              </select>
                              <label className="cover-upload-field compact-upload-field">
                                Обложка
                                <input type="file" accept="image/*" onChange={(event) => void uploadCoverFor("materials", material, event)} />
                                {coverUploadMessage("materials", material.id) ? <small>{coverUploadMessage("materials", material.id)}</small> : null}
                              </label>
                              <button className="chalk-button ghost" type="button" onClick={() => archiveEntity("materials", material.id)}>
                                В архив
                              </button>
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
                              <button
                                className="chalk-button ghost"
                                type="button"
                                onClick={() => saveEntity("lessons", { ...lesson, homeworkTemplateId: null })}
                              >
                                Отключить
                              </button>
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
                                  <option value="mentor,vip">mentor + vip</option>
                                  <option value="vip">vip</option>
                                  <option value="basic,mentor,vip">basic + mentor + vip</option>
                                  <option value="workshop,basic,mentor,vip">все тарифы</option>
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
                    );
                  })}
                </div>
              </details>
            ))}
          </div>
        </section>
      ) : null}

      <div className="action-row">
        <button className="chalk-button ghost" type="button" onClick={resetState}>
          Сбросить демо-данные
        </button>
      </div>
    </section>
  );
}
