import { mainModuleCatalog, mainTrainingBlueprint, workshopLessonCatalog, workshopTrainingBlueprint } from "./catalog";
import { ensureCover } from "./helpers";
import type {
  AccessPolicy,
  AppState,
  Folder,
  HomeworkAnswer,
  HomeworkTemplate,
  Lesson,
  LessonBlock,
  LessonProgress,
  Material,
  Module,
  Tariff,
  Training,
  User,
} from "./types";

const sampleVideo = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4";

function policy(tariffIds: AccessPolicy["tariffIds"], note: string, visibility: AccessPolicy["visibility"] = "show_locked") {
  return {
    tariffIds,
    visibility,
    sequential: false,
    durationMode: "rolling" as const,
    durationDays: null,
    note,
  };
}

const tariffs: Tariff[] = [
  {
    id: "zero",
    title: "Нулевой урок",
    priceLabel: "Бесплатно",
    tagline: "Закрытый вводный урок после прохождения опроса",
    accessWindow: "доступ по выданному логину",
    features: [
      "один вводный урок в личном кабинете",
      "доступ открывается только по аккаунту после опроса",
      "без показа на главной странице",
    ],
    highlight: "закрытый бесплатный доступ",
    sortOrder: 0,
  },
  {
    id: "workshop",
    title: "Воркшоп",
    priceLabel: "2 000 ₽",
    tagline: "Быстрый входной продукт с результатом за 1-2 дня",
    accessWindow: "доступ 14 дней",
    features: [
      "5 уроков и рабочий маршрут из ролика в Telegram",
      "шаблоны сценариев, CTA и мини-оффера",
      "быстрый результат без перегруза теорией",
    ],
    highlight: "короткий вход в систему",
    sortOrder: 1,
  },
  {
    id: "basic",
    title: "Базовый",
    priceLabel: "80 000 ₽",
    tagline: "Самостоятельное прохождение модулей 1-4",
    accessWindow: "доступ 3 месяца",
    features: [
      "модули 1-4 и все материалы базовой части",
      "контент, Telegram, оффер и первые продажи",
      "без проверок домашних и без чата с наставником",
    ],
    highlight: "запуск без хаоса",
    sortOrder: 2,
  },
  {
    id: "mentor",
    title: "С ментором",
    priceLabel: "120 000 ₽",
    tagline: "Полный трек модулей 1-7 с проверками и поддержкой",
    accessWindow: "доступ 6 месяцев",
    features: [
      "модули 1-7, домашки и проверка",
      "чат/Q&A, дополнительные материалы и разборы",
      "доступ к чату с наставником и центру готовых Reels",
    ],
    highlight: "внедрение и обратная связь",
    sortOrder: 3,
  },
  {
    id: "vip",
    title: "VIP",
    priceLabel: "150 000 ₽",
    tagline: "Все из тарифа с ментором плюс персональное сопровождение",
    accessWindow: "доступ навсегда",
    features: [
      "все модули, домашки и проверки без ограничения по времени",
      "личный чат, 2 созвона и персональные разборы",
      "максимальный доступ к материалам и приватным папкам",
    ],
    highlight: "персональный темп и помощь",
    sortOrder: 4,
  },
];

const users: User[] = [
  {
    id: "student-zero",
    role: "student",
    name: "Гость Нулевой урок",
    email: "zero@example.com",
    password: "chalk123",
    bio: "Бесплатный закрытый доступ к нулевому уроку после опроса.",
    createdAt: "2026-05-07T00:00:00.000Z",
    tariffId: "zero",
    expiresAt: null,
    trainingGrantIds: [],
  },
  {
    id: "student-workshop",
    role: "student",
    name: "Марина Воркшоп",
    email: "workshop@example.com",
    password: "chalk123",
    bio: "Тестовый доступ только к интенсиву.",
    createdAt: "2026-05-07T00:00:00.000Z",
    tariffId: "workshop",
    expiresAt: null,
    trainingGrantIds: [],
  },
  {
    id: "student-basic",
    role: "student",
    name: "Андрей Базовый",
    email: "basic@example.com",
    password: "chalk123",
    bio: "Самостоятельный проход базовой части.",
    createdAt: "2026-05-07T00:00:00.000Z",
    tariffId: "basic",
    expiresAt: "2026-08-01T00:00:00.000Z",
    trainingGrantIds: [],
  },
  {
    id: "student-mentor",
    role: "student",
    name: "Ольга Ментор",
    email: "mentor@example.com",
    password: "chalk123",
    bio: "Полный трек с домашками и менторской проверкой.",
    createdAt: "2026-05-07T00:00:00.000Z",
    tariffId: "mentor",
    expiresAt: "2026-11-01T00:00:00.000Z",
    trainingGrantIds: [],
  },
  {
    id: "student-vip",
    role: "student",
    name: "Никита VIP",
    email: "vip@example.com",
    password: "chalk123",
    bio: "Максимальный доступ и персональные разборы.",
    createdAt: "2026-05-07T00:00:00.000Z",
    tariffId: "vip",
    expiresAt: null,
    trainingGrantIds: [],
  },
  {
    id: "manager-demo",
    role: "manager",
    name: "Команда проверки",
    email: "review@example.com",
    password: "chalk123",
    bio: "Очередь домашних, статусы и комментарии.",
    createdAt: "2026-05-07T00:00:00.000Z",
    trainingGrantIds: [],
  },
  {
    id: "admin-demo",
    role: "admin",
    name: "Контент-оператор",
    email: "editor@example.com",
    password: "chalk123",
    bio: "Редактирование тренингов, модулей, уроков и доступов.",
    createdAt: "2026-05-07T00:00:00.000Z",
    trainingGrantIds: [],
  },
];

const trainings: Training[] = [];
const folders: Folder[] = [];
const modules: Module[] = [];
const lessons: Lesson[] = [];
const lessonBlocks: LessonBlock[] = [];
const materials: Material[] = [];
const homeworkTemplates: HomeworkTemplate[] = [];
const homeworkAnswers: HomeworkAnswer[] = [];
const progress: LessonProgress[] = [];

const mainTrainingId = "training-main";
const workshopTrainingId = "training-workshop";
const zeroTrainingId = "training-zero-lesson";

trainings.push(
  ensureCover({
    id: mainTrainingId,
    title: mainTrainingBlueprint.title,
    subtitle: mainTrainingBlueprint.subtitle,
    tagline: mainTrainingBlueprint.tagline,
    description: mainTrainingBlueprint.description,
    order: 1,
    status: "published",
    accessPolicy: policy(["basic", "mentor", "vip"], "Основной трек менторства"),
    coverStyle: "funnel",
    folderIds: [],
    moduleIds: [],
  }),
);

trainings.push(
  ensureCover({
    id: workshopTrainingId,
    title: workshopTrainingBlueprint.title,
    subtitle: workshopTrainingBlueprint.subtitle,
    tagline: workshopTrainingBlueprint.tagline,
    description: workshopTrainingBlueprint.description,
    order: 2,
    status: "published",
    accessPolicy: policy(["workshop"], "Интенсив доступен только участникам воркшопа"),
    coverStyle: "brief",
    folderIds: [],
    moduleIds: [],
  }),
);

trainings.push(
  ensureCover({
    id: zeroTrainingId,
    title: "Нулевой урок",
    subtitle: "Закрытый бесплатный вводный урок после опроса",
    tagline: "Доступ по выданному логину и паролю.",
    description:
      "Один вводный урок для людей, которые прошли опрос. Этот тренинг не показывается на главной странице и доступен только аккаунтам с тарифом «Нулевой урок».",
    order: 3,
    status: "published",
    accessPolicy: policy(["zero"], "Бесплатный закрытый доступ после опроса", "hide"),
    coverStyle: "brief",
    folderIds: [],
    moduleIds: [],
  }),
);

const zeroModuleId = "module-zero-1";
const zeroLessonId = "module-zero-1-lesson-1";
const zeroBlock1Id = `${zeroLessonId}-block-1`;
const zeroBlock2Id = `${zeroLessonId}-block-2`;
const zeroBlock3Id = `${zeroLessonId}-block-3`;
const zeroMaterialId = `${zeroLessonId}-material-1`;

const zeroModule: Module = ensureCover({
  id: zeroModuleId,
  trainingId: zeroTrainingId,
  title: "Нулевой урок",
  description: "Вводный урок перед выбором формата обучения: маршрут, логика программы и первый понятный шаг.",
  order: 1,
  status: "published",
  accessPolicy: policy(["zero"], "Открыт только бесплатному доступу после опроса", "hide"),
  coverStyle: "brief",
  lessonIds: [zeroLessonId],
});
modules.push(zeroModule);
trainings.find((training) => training.id === zeroTrainingId)?.moduleIds.push(zeroModuleId);

lessons.push(
  ensureCover({
    id: zeroLessonId,
    moduleId: zeroModuleId,
    title: "Нулевой урок: как устроен путь от контента к заявкам",
    description: "Закрытый вводный урок для тех, кто прошел опрос и получил доступ в личный кабинет.",
    summary:
      "Разбираем общую карту: почему контент должен вести в Telegram, как появляется заявка и какой следующий шаг выбрать под вашу ситуацию.",
    order: 1,
    status: "published",
    accessPolicy: policy(["zero"], "Закрытый бесплатный урок после опроса", "hide"),
    coverStyle: "brief",
    durationMinutes: 12,
    unlockDelayHours: 0,
    videoProvider: "external",
    videoUrl: sampleVideo,
    blockIds: [zeroBlock1Id, zeroBlock2Id, zeroBlock3Id],
    materialIds: [zeroMaterialId],
    homeworkTemplateId: null,
    timecodes: [
      { id: "timecode-zero-1", label: "Карта пути", seconds: 0, note: "Что смотрим в этом уроке" },
      { id: "timecode-zero-2", label: "Контент и Telegram", seconds: 180, note: "Как связать внимание и следующий шаг" },
      { id: "timecode-zero-3", label: "Что делать после просмотра", seconds: 480, note: "Как выбрать дальнейший формат" },
    ],
  }),
);

lessonBlocks.push(
  {
    id: zeroBlock1Id,
    lessonId: zeroLessonId,
    type: "text",
    title: "Зачем этот урок",
    body: "Это короткий вход в логику обучения: от первого касания в контенте до понятного перехода в Telegram и заявки.",
    bullets: [],
    order: 1,
    status: "published",
  },
  {
    id: zeroBlock2Id,
    lessonId: zeroLessonId,
    type: "checklist",
    title: "На что обратить внимание",
    body: "Смотрите не как теорию, а как диагностику своей текущей системы.",
    bullets: [
      "понятен ли один сегмент аудитории",
      "есть ли причина переходить из контента в Telegram",
      "есть ли следующий шаг после просмотра",
    ],
    order: 2,
    status: "published",
  },
  {
    id: zeroBlock3Id,
    lessonId: zeroLessonId,
    type: "cta",
    title: "После просмотра",
    body: "Зафиксируйте, где сейчас главный разрыв: в позиционировании, контенте, Telegram-переходе или продаже.",
    bullets: ["запишите один главный вывод", "подготовьте вопрос менеджеру", "выберите подходящий следующий формат"],
    order: 3,
    status: "published",
  },
);

materials.push(
  ensureCover({
    id: zeroMaterialId,
    title: "Конспект нулевого урока",
    description: "Короткая опора к вводному уроку.",
    order: 1,
    status: "published",
    parentType: "lesson",
    parentId: zeroLessonId,
    materialType: "text",
    body: "После просмотра отметьте текущую точку: что уже работает, где теряется внимание, какой следующий шаг нужен человеку после контента.",
    metaLabel: "конспект",
    accessPolicy: policy(["zero"], "Материал нулевого урока", "hide"),
    coverStyle: "brief",
  }),
);

const mainFoldersBlueprint = [
  {
    title: "Информационный канал в Telegram",
    description: "Официальный канал с объявлениями, расписанием и ссылками на обновления.",
    kind: "external" as const,
    externalUrl: "https://t.me/Valensky1",
    coverStyle: "notebook",
    accessPolicy: policy(["basic", "mentor", "vip"], "Открыт всем основным тарифам"),
    items: [],
  },
  {
    title: "Заполнить анкету",
    description: "Стартовая анкета, чтобы уточнить цель, нишу, статус контента и ближайший оффер.",
    kind: "external" as const,
    externalUrl: "https://t.me/valenskymanager",
    coverStyle: "brief",
    accessPolicy: policy(["basic", "mentor", "vip"], "Стартовое действие после входа"),
    items: [],
  },
  {
    title: "Общий чат в Telegram",
    description: "Комьюнити учеников для обсуждений, находок и быстрых вопросов по внедрению.",
    kind: "external" as const,
    externalUrl: "https://t.me/Valensky1",
    coverStyle: "network",
    accessPolicy: policy(["basic", "mentor", "vip"], "Открыт после входа в курс"),
    items: [],
  },
  {
    title: "Эгоцентр",
    description: "Папка с упражнениями на позиционирование, личный угол и экспертную рамку.",
    kind: "folder" as const,
    coverStyle: "ladder",
    accessPolicy: policy(["basic", "mentor", "vip"], "Материалы для работы над брендом"),
    items: [
      { title: "Карта личности", type: "text" as const, body: "Опишите свою историю, метод и тип трансформации, за которую вы хотите отвечать на рынке." },
      { title: "Шаблон «Я-ниша»", type: "template" as const, body: "Сужаемся не в профессию, а в понятный результат, ради которого за вами стоит следить." },
      { title: "Анкета узнаваемости", type: "file" as const, body: "Таблица для сбора смыслов, которым должны верить до покупки.", metaLabel: "Google Sheet" },
    ],
  },
  {
    title: "Чат с наставником",
    description: "Отдельный канал обратной связи для менторского и VIP доступа.",
    kind: "external" as const,
    externalUrl: "https://t.me/valenskymanager",
    coverStyle: "radar",
    accessPolicy: policy(["mentor", "vip"], "Открывается на тарифах с сопровождением"),
    items: [],
  },
  {
    title: "Библиотека",
    description: "Шаблоны, таблицы, гайды и документы по модулям 1-7.",
    kind: "folder" as const,
    coverStyle: "squares",
    accessPolicy: policy(["basic", "mentor", "vip"], "Коллекция практических материалов"),
    items: [
      { title: "100 хуков и заходов", type: "file" as const, body: "Банк заходов под Reels, Shorts и Telegram по разным сценарным задачам.", metaLabel: "PDF" },
      { title: "UTM + CAC/CPL/ROAS", type: "file" as const, body: "Таблица для первых запусков, сверки экономики и ручной атрибуции.", metaLabel: "Spreadsheet" },
      { title: "Platform-safe чеклист", type: "template" as const, body: "Проверка перед публикацией: AI-labels, safe zones, CTA, музыка, права." },
    ],
  },
  {
    title: "ChatGPT старая версия",
    description: "Папка с промптами и ограничениями под ручную AI-редактуру без AI-slop.",
    kind: "folder" as const,
    coverStyle: "notebook",
    accessPolicy: policy(["basic", "mentor", "vip"], "Промпты и редактура"),
    items: [
      { title: "Редактор идей", type: "prompt" as const, body: "Доработай идею по критериям: боль, широта, новизна, эмоция, связь с оффером." },
      { title: "Human proof", type: "prompt" as const, body: "Проверь текст на пустые общие фразы и добавь личный опыт, кейс, доказательство." },
    ],
  },
  {
    title: "ChatGPT новая версия",
    description: "Современный AI-production pipeline для research, scripts, repurposing и фактчека.",
    kind: "folder" as const,
    coverStyle: "network",
    accessPolicy: policy(["basic", "mentor", "vip"], "AI как контент-операционка"),
    items: [
      { title: "Pipeline research → script → edit", type: "prompt" as const, body: "Собери pipeline: ресерч, сценарий, фактчек, human voice, repurposing, аналитика." },
      { title: "Social search FAQ", type: "prompt" as const, body: "Собери список поисковых формулировок боли, FAQ и evergreen роликов под одну тему." },
    ],
  },
  {
    title: "Центр готовых Reels",
    description: "Шаблоны креативов и форматы тестов для paid + organic amplification.",
    kind: "folder" as const,
    coverStyle: "constellation",
    accessPolicy: policy(["mentor", "vip"], "Открывается после покупки сопровождения"),
    items: [
      { title: "Матрица 30 гипотез", type: "file" as const, body: "Creative testing lab для органики и рекламы с hook win-rate.", metaLabel: "Spreadsheet" },
      { title: "Creator brief", type: "template" as const, body: "Краткий бриф на creator-led ролики, usage rights и approvals." },
    ],
  },
  {
    title: "Нейро-Иван",
    description: "Персональный набор подсказок для сценариев, офферов и разборов узких мест в контенте.",
    kind: "folder" as const,
    coverStyle: "radar",
    accessPolicy: policy(["vip"], "Приватная папка VIP"),
    items: [
      { title: "Разбор узкого места", type: "text" as const, body: "Опиши один узкий участок воронки. Ниже ответь: что сломано, какой сигнал доходит до рынка, какой следующий шаг не считывается." },
      { title: "Личный план на 14 дней", type: "template" as const, body: "Персональная карта публикаций, прогрева, Telegram и paid amplification." },
    ],
  },
];

mainFoldersBlueprint.forEach((blueprint, index) => {
  const folderId = `folder-main-${index + 1}`;
  const folder: Folder = ensureCover({
    id: folderId,
    title: blueprint.title,
    description: blueprint.description,
    order: index + 1,
    status: "published",
    trainingId: mainTrainingId,
    parentFolderId: null,
    kind: blueprint.kind,
    externalUrl: blueprint.externalUrl,
    itemIds: [],
    accessPolicy: blueprint.accessPolicy,
    coverStyle: blueprint.coverStyle,
  });

  folders.push(folder);
  trainings[0].folderIds.push(folderId);

  blueprint.items.forEach((item, itemIndex) => {
    const materialId = `material-folder-main-${index + 1}-${itemIndex + 1}`;
    materials.push(
      ensureCover({
        id: materialId,
        title: item.title,
        description: item.body,
        order: itemIndex + 1,
        status: "published",
        parentType: "folder",
        parentId: folderId,
        materialType: item.type,
        body: item.body,
        metaLabel: "metaLabel" in item ? item.metaLabel : undefined,
        accessPolicy: folder.accessPolicy,
        coverStyle: folder.coverStyle,
      }),
    );
    folder.itemIds.push(materialId);
  });
});

const workshopFoldersBlueprint = [
  {
    title: "Вводный канал",
    description: "Короткие инструкции к воркшопу и канал с быстрыми обновлениями.",
    kind: "external" as const,
    externalUrl: "https://t.me/Valensky1",
    coverStyle: "brief",
    accessPolicy: policy(["workshop"], "Открыт участникам воркшопа"),
    items: [],
  },
  {
    title: "Рабочая тетрадь воркшопа",
    description: "Краткие шаблоны рабочей тетради, чтобы собрать маршрут за 5 уроков.",
    kind: "folder" as const,
    coverStyle: "notebook",
    accessPolicy: policy(["workshop"], "Рабочая тетрадь интенсива"),
    items: [
      { title: "Формула позиционирования", type: "template" as const, body: "Кому помогаю, из какой точки в какую, через какой подход и без какого препятствия." },
      { title: "Scoring идей", type: "file" as const, body: "Таблица оценки боли, широты, новизны, эмоции и связи с оффером.", metaLabel: "Spreadsheet" },
      { title: "Спринт на 7 дней", type: "template" as const, body: "Чеклист публикаций, Telegram CTA и первых метрик на неделю." },
    ],
  },
];

workshopFoldersBlueprint.forEach((blueprint, index) => {
  const folderId = `folder-workshop-${index + 1}`;
  const folder: Folder = ensureCover({
    id: folderId,
    title: blueprint.title,
    description: blueprint.description,
    order: index + 1,
    status: "published",
    trainingId: workshopTrainingId,
    parentFolderId: null,
    kind: blueprint.kind,
    externalUrl: blueprint.externalUrl,
    itemIds: [],
    accessPolicy: blueprint.accessPolicy,
    coverStyle: blueprint.coverStyle,
  });
  folders.push(folder);
  trainings[1].folderIds.push(folderId);
  blueprint.items.forEach((item, itemIndex) => {
    const materialId = `material-folder-workshop-${index + 1}-${itemIndex + 1}`;
    materials.push(
      ensureCover({
        id: materialId,
        title: item.title,
        description: item.body,
        order: itemIndex + 1,
        status: "published",
        parentType: "folder",
        parentId: folderId,
        materialType: item.type,
        body: item.body,
        metaLabel: "metaLabel" in item ? item.metaLabel : undefined,
        accessPolicy: folder.accessPolicy,
        coverStyle: folder.coverStyle,
      }),
    );
    folder.itemIds.push(materialId);
  });
});

mainModuleCatalog.forEach((moduleBlueprint, moduleIndex) => {
  const moduleId = `module-main-${moduleIndex + 1}`;
  const allowedTariffs: AccessPolicy["tariffIds"] = moduleIndex <= 3 ? ["basic", "mentor", "vip"] : ["mentor", "vip"];
  const module: Module = ensureCover({
    id: moduleId,
    trainingId: mainTrainingId,
    title: moduleBlueprint.title,
    description: moduleBlueprint.description,
    order: moduleIndex + 1,
    status: "published",
    accessPolicy: policy(allowedTariffs, moduleIndex <= 3 ? "Входит в базовую часть" : "Открывается на тарифах с сопровождением"),
    coverStyle: moduleBlueprint.coverStyle,
    lessonIds: [],
  });
  modules.push(module);
  trainings[0].moduleIds.push(moduleId);

  moduleBlueprint.lessons.forEach((lessonTitle, lessonIndex) => {
    const lessonId = `${moduleId}-lesson-${lessonIndex + 1}`;
    const block1Id = `${lessonId}-block-1`;
    const block2Id = `${lessonId}-block-2`;
    const block3Id = `${lessonId}-block-3`;
    const material1Id = `${lessonId}-material-1`;
    const material2Id = `${lessonId}-material-2`;
    const isHomeworkLesson = lessonIndex === moduleBlueprint.lessons.length - 1 || lessonIndex === Math.floor(moduleBlueprint.lessons.length / 2);
    const homeworkId = isHomeworkLesson ? `${lessonId}-homework` : null;

    const lesson: Lesson = ensureCover({
      id: lessonId,
      moduleId,
      title: lessonTitle,
      description: `${moduleBlueprint.shortTitle}. ${lessonTitle}.`,
      summary: `Этот урок помогает пройти точку модуля «${moduleBlueprint.shortTitle}» без хаоса и сразу перевести вывод в действие.`,
      order: lessonIndex + 1,
      status: "published",
      accessPolicy: policy(allowedTariffs, module.accessPolicy.note),
      coverStyle: moduleBlueprint.coverStyle,
      durationMinutes: 10 + ((lessonIndex + moduleIndex) % 6),
      unlockDelayHours: 0,
      videoProvider: "external",
      videoUrl: sampleVideo,
      blockIds: [block1Id, block2Id, block3Id],
      materialIds: [material1Id, material2Id],
      homeworkTemplateId: homeworkId,
    });

    lessons.push(lesson);
    module.lessonIds.push(lessonId);

    lessonBlocks.push(
      {
        id: block1Id,
        lessonId,
        type: "text",
        title: "Что разбираем в уроке",
        body: `${lessonTitle} встроен в результат модуля: ${moduleBlueprint.description}`,
        bullets: [],
        order: 1,
      },
      {
        id: block2Id,
        lessonId,
        type: "checklist",
        title: "На что смотреть во время просмотра",
        body: "Держите рядом рабочую тетрадь и отмечайте конкретные решения, которые перенесете в систему.",
        bullets: moduleBlueprint.results.slice(0, 3),
        order: 2,
      },
      {
        id: block3Id,
        lessonId,
        type: "cta",
        title: "Что сделать сразу после урока",
        body: moduleBlueprint.homeworkPrompt,
        bullets: moduleBlueprint.artifacts.slice(0, 3),
        order: 3,
      },
    );

    materials.push(
      ensureCover({
        id: material1Id,
        title: moduleBlueprint.artifacts[lessonIndex % moduleBlueprint.artifacts.length],
        description: "Практический материал к уроку.",
        order: 1,
        status: "published",
        parentType: "lesson",
        parentId: lessonId,
        materialType: lessonIndex % 2 === 0 ? "file" : "template",
        body: moduleBlueprint.homeworkPrompt,
        metaLabel: lessonIndex % 2 === 0 ? "PDF / Sheet" : "Шаблон",
        accessPolicy: lesson.accessPolicy,
        coverStyle: moduleBlueprint.coverStyle,
      }),
      ensureCover({
        id: material2Id,
        title: `Чеклист: ${lessonTitle}`,
        description: "Короткая опора для внедрения после просмотра.",
        order: 2,
        status: "published",
        parentType: "lesson",
        parentId: lessonId,
        materialType: "text",
        body: `Сверьте урок с практическим результатом модуля: ${moduleBlueprint.results.join("; ")}.`,
        metaLabel: "Конспект",
        accessPolicy: lesson.accessPolicy,
        coverStyle: moduleBlueprint.coverStyle,
      }),
    );

    if (homeworkId) {
      homeworkTemplates.push({
        id: homeworkId,
        lessonId,
        title: `Домашка: ${lessonTitle}`,
        prompt: moduleBlueprint.homeworkPrompt,
        checklist: moduleBlueprint.results.slice(0, 4),
        requiredTariffIds: ["mentor", "vip"],
      });
    }
  });
});

const workshopModuleId = "module-workshop-1";
const workshopModule: Module = ensureCover({
  id: workshopModuleId,
  trainingId: workshopTrainingId,
  title: "Контент и трафик без магии: маршрут от идеи до заявки",
  description: "Пять уроков из карты воркшопа: один угол, идеи, сценарии, Telegram-переход, мини-оффер и 7-дневный спринт.",
  order: 1,
  status: "published",
  accessPolicy: policy(["workshop"], "Открыт участникам воркшопа"),
  coverStyle: "brief",
  lessonIds: [],
});
modules.push(workshopModule);
trainings[1].moduleIds.push(workshopModuleId);

workshopLessonCatalog.forEach((lessonBlueprint, lessonIndex) => {
  const lessonId = `${workshopModuleId}-lesson-${lessonIndex + 1}`;
  const block1Id = `${lessonId}-block-1`;
  const block2Id = `${lessonId}-block-2`;
  const block3Id = `${lessonId}-block-3`;
  const material1Id = `${lessonId}-material-1`;

  lessons.push(
    ensureCover({
      id: lessonId,
      moduleId: workshopModuleId,
      title: lessonBlueprint.title,
      description: lessonBlueprint.summary,
      summary: lessonBlueprint.summary,
      order: lessonIndex + 1,
      status: "published",
      accessPolicy: policy(["workshop"], "Воркшоп без дополнительных домашних"),
      coverStyle: "brief",
      durationMinutes: lessonIndex < 2 ? 10 : 11,
      unlockDelayHours: 0,
      videoProvider: "external",
      videoUrl: sampleVideo,
      blockIds: [block1Id, block2Id, block3Id],
      materialIds: [material1Id],
      homeworkTemplateId: null,
    }),
  );
  workshopModule.lessonIds.push(lessonId);

  lessonBlocks.push(
    {
      id: block1Id,
      lessonId,
      type: "text",
      title: "Смысл урока",
      body: lessonBlueprint.summary,
      bullets: [],
      order: 1,
    },
    {
      id: block2Id,
      lessonId,
      type: "checklist",
      title: "Ключевые мысли",
      body: "Держим фокус на одной рабочей связке: ролик → Telegram → следующий шаг.",
      bullets: lessonBlueprint.talkingPoints,
      order: 2,
    },
    {
      id: block3Id,
      lessonId,
      type: "cta",
      title: "Действие после урока",
      body: lessonBlueprint.artifact,
      bullets: lessonBlueprint.action,
      order: 3,
    },
  );

  materials.push(
    ensureCover({
      id: material1Id,
      title: `Артефакт: ${lessonBlueprint.artifact}`,
      description: "Что должно остаться у вас на руках после выполнения урока.",
      order: 1,
      status: "published",
      parentType: "lesson",
      parentId: lessonId,
      materialType: "text",
      body: `${lessonBlueprint.artifact}. Затем сделайте: ${lessonBlueprint.action.join("; ")}.`,
      metaLabel: "Workbook",
      accessPolicy: policy(["workshop"], "Материал воркшопа"),
      coverStyle: "brief",
    }),
  );
});

progress.push(
  {
    id: "progress-workshop-lesson-1",
    lessonId: "module-workshop-1-lesson-1",
    studentId: "student-workshop",
    watchedSeconds: 512,
    durationSeconds: 600,
    lastPositionSeconds: 498,
    isCompleted: true,
    updatedAt: "2026-05-05T12:10:00.000Z",
  },
  {
    id: "progress-workshop-lesson-2",
    lessonId: "module-workshop-1-lesson-2",
    studentId: "student-workshop",
    watchedSeconds: 260,
    durationSeconds: 600,
    lastPositionSeconds: 260,
    isCompleted: false,
    updatedAt: "2026-05-05T12:30:00.000Z",
  },
  {
    id: "progress-basic-main-1",
    lessonId: "module-main-1-lesson-1",
    studentId: "student-basic",
    watchedSeconds: 640,
    durationSeconds: 720,
    lastPositionSeconds: 640,
    isCompleted: true,
    updatedAt: "2026-05-04T10:10:00.000Z",
  },
  {
    id: "progress-basic-main-2",
    lessonId: "module-main-1-lesson-2",
    studentId: "student-basic",
    watchedSeconds: 700,
    durationSeconds: 720,
    lastPositionSeconds: 700,
    isCompleted: true,
    updatedAt: "2026-05-04T10:45:00.000Z",
  },
  {
    id: "progress-basic-main-3",
    lessonId: "module-main-1-lesson-3",
    studentId: "student-basic",
    watchedSeconds: 280,
    durationSeconds: 720,
    lastPositionSeconds: 280,
    isCompleted: false,
    updatedAt: "2026-05-04T11:10:00.000Z",
  },
  {
    id: "progress-mentor-main-5",
    lessonId: "module-main-2-lesson-5",
    studentId: "student-mentor",
    watchedSeconds: 710,
    durationSeconds: 720,
    lastPositionSeconds: 710,
    isCompleted: true,
    updatedAt: "2026-05-03T09:10:00.000Z",
  },
  {
    id: "progress-mentor-main-6",
    lessonId: "module-main-2-lesson-6",
    studentId: "student-mentor",
    watchedSeconds: 522,
    durationSeconds: 720,
    lastPositionSeconds: 522,
    isCompleted: false,
    updatedAt: "2026-05-03T09:40:00.000Z",
  },
  {
    id: "progress-vip-main-5-3",
    lessonId: "module-main-5-lesson-3",
    studentId: "student-vip",
    watchedSeconds: 720,
    durationSeconds: 720,
    lastPositionSeconds: 720,
    isCompleted: true,
    updatedAt: "2026-05-02T17:00:00.000Z",
  },
);

homeworkAnswers.push(
  {
    id: "hw-mentor-positioning",
    lessonId: "module-main-1-lesson-8",
    studentId: "student-mentor",
    text: "Собрала позиционирование, карту болей и 24 темы. Самое узкое место было в формулировке обещания и CTA на переход в Telegram.",
    attachments: [{ name: "positioning-board.pdf", size: 128400, type: "application/pdf" }],
    status: "in_review",
    reviewerComment: "Проверяю формулировку обещания и точку перехода.",
    submittedAt: "2026-05-03T10:10:00.000Z",
    updatedAt: "2026-05-03T10:20:00.000Z",
    reviewerId: "manager-demo",
  },
  {
    id: "hw-vip-content-lab",
    lessonId: "module-main-3-lesson-14",
    studentId: "student-vip",
    text: "Разложил AI-production pipeline и подготовил 54 темы. Хочу обратную связь по FAQ/evergreen и по качеству repurposing.",
    attachments: [{ name: "content-lab.xlsx", size: 99210, type: "application/vnd.ms-excel" }],
    status: "accepted",
    reviewerComment: "Сильная матрица. Отдельно дожми CTA в блоке FAQ.",
    submittedAt: "2026-05-01T14:40:00.000Z",
    updatedAt: "2026-05-02T09:10:00.000Z",
    reviewerId: "manager-demo",
  },
  {
    id: "hw-vip-offer-draft",
    lessonId: "module-main-4-lesson-8",
    studentId: "student-vip",
    text: "Оффер собран, но сомневаюсь в формулировке для холодной аудитории.",
    attachments: [{ name: "offer-draft.txt", size: 3200, type: "text/plain" }],
    status: "revision",
    reviewerComment: "Сделай обещание менее общим и привяжи к одному острому симптому.",
    submittedAt: "2026-05-02T13:10:00.000Z",
    updatedAt: "2026-05-02T15:20:00.000Z",
    reviewerId: "manager-demo",
  },
);

export const defaultState: AppState = {
  tariffs,
  users,
  trainings,
  folders,
  modules,
  lessons,
  lessonBlocks,
  materials,
  homeworkTemplates,
  homeworkAnswers,
  progress,
};
