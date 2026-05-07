# Index.md — навигация по проекту

Проект: учебная платформа `Менторство Валенского` в логике GetCourse и визуальном стиле черной доски с белым мелом.

Это Vite + React + TypeScript приложение с локальным Node API: публичный лендинг, вход, кабинет ученика, тренинги, полезные папки, модули, уроки, материалы, домашки, менеджерская проверка и демо-админка контента.

После аудита по PRD усилены guard-слои: прямые URL проверяют родительскую цепочку, `sequential` работает только когда включен, материалы не раскрывают тело/ссылки без доступа, `/admin` закрыт для не-админов, логин идет через httpOnly cookie, сессии живут в локальном файловом store, а домашние файлы и обложки загружаются в `server/uploads`.

## Оглавление

1. [Быстрый запуск](#быстрый-запуск)
2. [Дерево проекта](#дерево-проекта)
3. [Ключевые файлы](#ключевые-файлы)
4. [Маршруты приложения](#маршруты-приложения)
5. [Демо-доступы](#демо-доступы)
6. [Данные и доступы](#данные-и-доступы)
7. [Основные пользовательские сценарии](#основные-пользовательские-сценарии)
8. [Где что менять](#где-что-менять)
9. [Проверка проекта](#проверка-проекта)
10. [Production-заметки](#production-заметки)

## Быстрый запуск

```bash
npm install
npm run dev
```

Команда `npm run dev` экспортирует seed-данные, запускает локальный API и Vite:

```text
API: http://127.0.0.1:8787/
Web: http://127.0.0.1:4173/
```

Если web-порт занят, Vite выберет следующий свободный порт. API-порт можно изменить через `API_PORT`.

Команды из [package.json](package.json):

```bash
npm run dev      # локальная разработка: API + web
npm run dev:web  # только Vite frontend
npm run api      # только локальный backend/API
npm run seed:export # пересобрать server/data из src/domain/seed.ts
npm run build    # TypeScript + production build
npm run preview  # preview production build
```

## Дерево проекта

```text
САЙТ ГЕТКУРС/
  index.html
  package.json
  vite.config.ts
  tsconfig.json
  scripts/
    dev.mjs
    export-seed.mjs
  server/
    server.mjs
    data/
      seed-state.json
      app-state.json
    uploads/
  src/
    main.tsx
    styles.css
    app/
      App.tsx
      context.tsx
    components/
      AppLayout.tsx
      ui.tsx
    domain/
      types.ts
      api.ts
      catalog.ts
      seed.ts
      helpers.ts
    pages/
      HomePage.tsx
      LoginPage.tsx
      TrainingsPage.tsx
      TrainingPage.tsx
      FolderPage.tsx
      ModulePage.tsx
      LessonPage.tsx
      AccessDeniedPage.tsx
      AdminPage.tsx
      ManagerHomeworksPage.tsx
      LegalPage.tsx
```

## Ключевые файлы

- [src/main.tsx](src/main.tsx) — точка входа React, подключение роутера, провайдера состояния и CSS.
- [src/app/App.tsx](src/app/App.tsx) — карта маршрутов приложения.
- [src/app/context.tsx](src/app/context.tsx) — глобальное состояние, async bootstrap, login/logout, сохранение сущностей, домашки, прогресс.
- [src/components/AppLayout.tsx](src/components/AppLayout.tsx) — общий layout: шапка, навигация, user-chip, footer.
- [src/components/ui.tsx](src/components/ui.tsx) — переиспользуемые UI-блоки: breadcrumbs, cover, access panel, cards.
- [src/domain/types.ts](src/domain/types.ts) — типы тарифов, ролей, тренингов, модулей, уроков, материалов, домашек.
- [src/domain/api.ts](src/domain/api.ts) — клиент локального API: bootstrap, login, reset, entities, homework, progress, uploads.
- [src/domain/catalog.ts](src/domain/catalog.ts) — программа курса и воркшопа как структурированный каталог.
- [src/domain/seed.ts](src/domain/seed.ts) — server-seed: тарифы, пользователи, тренинги, папки, модули, 82 урока, материалы, домашки.
- [src/domain/helpers.ts](src/domain/helpers.ts) — проверки доступа, material-level access, `show_locked`/`hide`, счетчики уроков, сортировки, cover SVG, статусы.
- [server/server.mjs](server/server.mjs) — локальный backend: API, JSON-state, httpOnly cookie, file-session store, upload/download домашних файлов и обложек.
- [server/data](server/data) — `seed-state.json` и рабочий `app-state.json`.
- [server/uploads](server/uploads) — локальное хранилище загруженных файлов.
- [scripts/export-seed.mjs](scripts/export-seed.mjs) — экспортирует `defaultState` в server JSON.
- [scripts/dev.mjs](scripts/dev.mjs) — запускает API и Vite вместе.
- [src/pages](src/pages) — страницы приложения.
- [src/styles.css](src/styles.css) — весь визуальный слой: доска, мел, сетки, формы, карточки, mobile.

## Маршруты приложения

Маршруты описаны в [src/app/App.tsx](src/app/App.tsx).

| Route | Назначение |
| --- | --- |
| `/` | Главная страница: описание курса, программа, 4 тарифа, Telegram-ссылки, legal footer |
| `/login` | Страница входа |
| `/trainings` | Список доступных тренингов ученика |
| `/trainings/:trainingId` | Страница тренинга: тариф, обложка, полезные блоки, модули |
| `/trainings/:trainingId/folders/:folderId` | Полезная папка или материал |
| `/trainings/:trainingId/modules/:moduleId` | Модуль со списком уроков |
| `/trainings/:trainingId/modules/:moduleId/lessons/:lessonId` | Страница урока: видео, материалы, домашка |
| `/access-denied` | Закрытый доступ с причиной и CTA |
| `/manager/homeworks` | Очередь домашних заданий для проверки |
| `/manager/students/:studentId` | Карточка ученика для менеджера и админа |
| `/admin` | Демо-админка контента и доступов, доступна только роли `admin` |
| `/legal/privacy` | Политика конфиденциальности |
| `/legal/terms` | Пользовательское соглашение |

Быстрые прямые ссылки на seed-тренинги:

- `/trainings/training-main` — основная программа.
- `/trainings/training-workshop` — воркшоп.

## Демо-доступы

Пароль для всех демо-пользователей:

```text
chalk123
```

| Логин | Роль / доступ | Что проверить |
| --- | --- | --- |
| `workshop@example.com` | ученик, Воркшоп | видит только воркшоп на 5 уроков |
| `basic@example.com` | ученик, Базовый | видит основную программу, модули 1-4, закрытые модули 5-7 |
| `mentor@example.com` | ученик, С ментором | видит полный трек и домашки с проверкой |
| `vip@example.com` | ученик, VIP | видит полный трек и VIP-папки |
| `review@example.com` | менеджер | попадает в `/manager/homeworks` |
| `editor@example.com` | админ / редактор | попадает в `/admin` |

## Данные и доступы

Главная модель проекта находится в [src/domain](src/domain), а рабочие данные обслуживает [server/server.mjs](server/server.mjs):

- [types.ts](src/domain/types.ts) задает сущности: `Tariff`, `User`, `Training`, `Folder`, `Module`, `Lesson`, `Material`, `HomeworkTemplate`, `HomeworkAnswer`, `AccessPolicy`.
- [catalog.ts](src/domain/catalog.ts) хранит содержательную программу курса и воркшопа.
- [seed.ts](src/domain/seed.ts) собирает стартовое состояние, которое экспортируется в `server/data/seed-state.json`.
- [helpers.ts](src/domain/helpers.ts) проверяет доступы, считает опубликованные уроки, ищет сущности и форматирует статусы.
- [api.ts](src/domain/api.ts) отправляет все изменения в локальный API.
- `server/data/app-state.json` хранит текущее состояние между перезапусками.
- `server/uploads` хранит файлы домашних заданий, а менеджер видит ссылки на них в очереди проверки.

Тарифы:

- `workshop`
- `basic`
- `mentor`
- `vip`

Роли:

- `student`
- `manager`
- `admin`

Важные инварианты:

- На главной ровно 4 тарифа.
- Счетчик уроков считается из опубликованных уроков, а не прописан вручную.
- Ученик видит доступные тренинги и locked-тренинги только при `visibility: show_locked`.
- `visibility: hide` скрывает закрытые блоки из списков.
- Закрытые папки, модули, уроки и материалы показывают причину, но не открывают приватный контент.
- Прямые URL сверяют `trainingId -> folder/module -> lesson`.
- Админка меняет данные через API без правки кода.
- Пароли в локальном state хранятся как `scrypt` hash и не отдаются в клиентский DTO: сервер возвращает пользователей с пустым `password`.

## Основные пользовательские сценарии

### Гость

1. Открывает `/`.
2. Видит описание курса, программу, 4 тарифа.
3. Переходит в Telegram-группу или поддержку.
4. Нажимает `Войти`.

### Ученик

1. Открывает `/login`.
2. Входит одним из student-доступов.
3. Попадает в `/trainings`.
4. Открывает доступный тренинг.
5. Видит тариф над обложкой, полезные блоки и модули.
6. Открывает модуль и урок.
7. Смотрит видео, материалы и домашку, если она доступна на тарифе.

### Менеджер

1. Входит как `review@example.com`.
2. Попадает в `/manager/homeworks`.
3. Видит ответы учеников, тариф, тренинг, модуль, урок, файлы.
4. Открывает карточку ученика с тарифом, доступами, статистикой и историей домашних заданий.
5. Меняет статус: `Отправлена`, `На проверке`, `Принята`, `Нужна доработка`.

### Админ

1. Входит как `editor@example.com`.
2. Попадает в `/admin`.
3. Редактирует тарифы, тренинги, статусы, реальные обложки, вложенные папки и политики доступа.
4. Создает тренинги, папки, вложенные папки, внешние блоки, материалы, модули и уроки.
5. Редактирует видео URL, порядок, перенос уроков между модулями, материалы урока и шаблоны домашних заданий.
6. Сбрасывает demo-state к seed-данным при необходимости.

## Где что менять

| Нужно изменить | Файл |
| --- | --- |
| Текст лендинга и публичные блоки | [src/pages/HomePage.tsx](src/pages/HomePage.tsx) |
| Демо-логины на форме входа | [src/pages/LoginPage.tsx](src/pages/LoginPage.tsx) |
| Верхняя навигация и footer | [src/components/AppLayout.tsx](src/components/AppLayout.tsx) |
| Общие карточки, breadcrumbs, access panel | [src/components/ui.tsx](src/components/ui.tsx) |
| Программа курса, модули, уроки, результаты | [src/domain/catalog.ts](src/domain/catalog.ts) |
| Тарифы, пользователи, seed-тренинги, папки, материалы | [src/domain/seed.ts](src/domain/seed.ts) |
| Правила доступа и счетчики | [src/domain/helpers.ts](src/domain/helpers.ts) |
| Редактор контента, папок, материалов, видео и домашних | [src/pages/AdminPage.tsx](src/pages/AdminPage.tsx) |
| Проверка домашних менеджером | [src/pages/ManagerHomeworksPage.tsx](src/pages/ManagerHomeworksPage.tsx) |
| Визуальный стиль доски и мела | [src/styles.css](src/styles.css) |
| Маршруты | [src/app/App.tsx](src/app/App.tsx) |
| API, сессии, JSON-state, uploads | [server/server.mjs](server/server.mjs) |

## Проверка проекта

Минимальная проверка:

```bash
npm run build
```

Ручной smoke-check:

1. Открыть `/`.
2. Проверить, что на главной 4 тарифа.
3. Войти как `basic@example.com`.
4. Открыть `/trainings` и основной тренинг.
5. Убедиться, что модули 1-4 открыты, а 5-7 закрыты на базовом тарифе.
6. Войти как `vip@example.com` и проверить полный доступ.
7. Войти как `review@example.com` и открыть `/manager/homeworks`.
8. Войти как `editor@example.com` и открыть `/admin`.
9. Проверить прямой неверный URL: `/trainings/training-workshop/modules/module-main-1` должен показать закрытый/не найденный доступ, а не чужой модуль.
10. Войти как `mentor@example.com`, открыть урок с домашкой, прикрепить файл и отправить ответ.
11. Войти как `review@example.com`, открыть `/manager/homeworks` и проверить, что файл домашки открывается ссылкой.
12. Проверить mobile viewport 320px: шапка должна быть компактной, без перекрытия основного контента.

Последний smoke-check артефакт:

- [output/playwright/mobile-lesson-smoke.png](output/playwright/mobile-lesson-smoke.png)

## Production-заметки

- Локальный backend/API есть: данные живут в `server/data/app-state.json`, сессии в `server/data/session-store.json`, файлы сохраняются в `server/uploads`.
- Для production JSON-state нужно заменить на БД, а `server/uploads` — на объектное хранилище или файловый сервис.
- Видео использует demo-URL.
- Юридические страницы содержат демо-текст, перед публикацией их нужно заменить финальными документами.
- Админка подключена к локальному API и покрывает основные CMS-поля; для production стоит вынести ее в серверную CMS или набор typed endpoints с аудитом изменений.
- Роли и доступы имеют локальную серверную проверку; для production нужны полноценные политики доступа, аудит действий и rate limit на авторизацию.
