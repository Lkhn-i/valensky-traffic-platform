import { createReadStream } from "node:fs";
import { copyFile, mkdir, readFile, rename, stat, writeFile } from "node:fs/promises";
import http from "node:http";
import { extname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { randomBytes, randomUUID, scryptSync, timingSafeEqual } from "node:crypto";

const rootDir = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const dataDir = join(rootDir, "server", "data");
const uploadDir = join(rootDir, "server", "uploads");
const coverUploadDir = join(uploadDir, "covers");
const seedPath = join(dataDir, "seed-state.json");
const statePath = join(dataDir, "app-state.json");
const sessionStorePath = join(dataDir, "session-store.json");
const sessionCookieName = "chalk_session";
const sessionMaxAgeSeconds = 60 * 60 * 24 * 30;
const passwordHashPrefix = "scrypt";
const port = Number(process.env.API_PORT || 8787);
let writeQueue = Promise.resolve();
let sessionWriteQueue = Promise.resolve();
const sessions = new Map();
const uploadOwners = new Map();

const entityKeys = new Set([
  "tariffs",
  "users",
  "trainings",
  "folders",
  "modules",
  "lessons",
  "lessonBlocks",
  "materials",
  "homeworkTemplates",
  "homeworkAnswers",
  "progress",
]);

function sendJson(response, status, payload, headers = {}) {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    ...headers,
  });
  response.end(JSON.stringify(payload));
}

function sendError(response, status, message) {
  sendJson(response, status, { ok: false, message });
}

function parseCookies(request) {
  const header = request.headers.cookie || "";
  return Object.fromEntries(
    header
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const [key, ...value] = part.split("=");
        return [key, decodeURIComponent(value.join("="))];
      }),
  );
}

function isHashedPassword(value) {
  return typeof value === "string" && value.startsWith(`${passwordHashPrefix}$`);
}

function hashPassword(password) {
  const salt = randomBytes(16).toString("hex");
  const hash = scryptSync(password, salt, 64).toString("hex");
  return `${passwordHashPrefix}$${salt}$${hash}`;
}

function verifyHashedPassword(password, storedPassword) {
  const [, salt, hash] = storedPassword.split("$");
  if (!salt || !hash) {
    return false;
  }
  const expectedHash = Buffer.from(hash, "hex");
  const actualHash = scryptSync(password, salt, expectedHash.length);
  return expectedHash.length === actualHash.length && timingSafeEqual(expectedHash, actualHash);
}

function verifyPassword(password, storedPassword) {
  if (!storedPassword) {
    return false;
  }
  return isHashedPassword(storedPassword)
    ? verifyHashedPassword(password, storedPassword)
    : storedPassword === password;
}

function createSessionRecord(userId) {
  return {
    userId,
    maxAge: sessionMaxAgeSeconds,
    expiresAt: new Date(Date.now() + sessionMaxAgeSeconds * 1000).toISOString(),
  };
}

function pruneExpiredSessions() {
  let changed = false;
  for (const [sessionId, session] of sessions) {
    if (!session?.userId || Date.parse(session.expiresAt || "") <= Date.now()) {
      sessions.delete(sessionId);
      changed = true;
    }
  }
  return changed;
}

function serializeSessions() {
  return {
    sessions: [...sessions.entries()].map(([id, session]) => ({
      id,
      userId: session.userId,
      expiresAt: session.expiresAt,
      maxAge: session.maxAge,
    })),
  };
}

async function writeSessionStore() {
  await ensureDataFiles();
  const tempPath = `${sessionStorePath}.${randomUUID()}.tmp`;
  await writeFile(tempPath, `${JSON.stringify(serializeSessions(), null, 2)}\n`);
  await rename(tempPath, sessionStorePath);
}

function persistSessions() {
  const task = sessionWriteQueue.then(async () => {
    pruneExpiredSessions();
    await writeSessionStore();
  });
  sessionWriteQueue = task.catch(() => {});
  return task;
}

async function loadSessionStore() {
  await ensureDataFiles();
  sessions.clear();
  const payload = JSON.parse(await readFile(sessionStorePath, "utf8"));
  for (const entry of Array.isArray(payload.sessions) ? payload.sessions : []) {
    if (!entry?.id || !entry?.userId || !entry?.expiresAt) {
      continue;
    }
    sessions.set(String(entry.id), {
      userId: String(entry.userId),
      expiresAt: String(entry.expiresAt),
      maxAge: Number(entry.maxAge) > 0 ? Number(entry.maxAge) : sessionMaxAgeSeconds,
    });
  }
  if (pruneExpiredSessions()) {
    await persistSessions();
  }
}

async function createSessionCookie(userId) {
  const sessionId = randomUUID();
  sessions.set(sessionId, createSessionRecord(userId));
  await persistSessions();
  return `${sessionCookieName}=${encodeURIComponent(sessionId)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${sessionMaxAgeSeconds}`;
}

function clearSessionCookie() {
  return `${sessionCookieName}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`;
}

async function ensureDataFiles() {
  await mkdir(dataDir, { recursive: true });
  await mkdir(uploadDir, { recursive: true });
  await mkdir(coverUploadDir, { recursive: true });
  try {
    await stat(seedPath);
  } catch {
    throw new Error("Seed data is missing. Run `npm run seed:export` before starting the API server.");
  }
  try {
    await stat(statePath);
  } catch {
    await copyFile(seedPath, statePath);
  }
  try {
    await stat(sessionStorePath);
  } catch {
    await writeFile(sessionStorePath, `${JSON.stringify({ sessions: [] }, null, 2)}\n`);
  }
}

async function readState() {
  await ensureDataFiles();
  return JSON.parse(await readFile(statePath, "utf8"));
}

async function writeState(state) {
  await ensureDataFiles();
  const tempPath = `${statePath}.${randomUUID()}.tmp`;
  await writeFile(tempPath, `${JSON.stringify(state, null, 2)}\n`);
  await rename(tempPath, statePath);
}

async function resetStateFile() {
  await ensureDataFiles();
  await copyFile(seedPath, statePath);
  return readState();
}

function sanitizeState(state) {
  return {
    ...state,
    users: state.users.map((user) => ({ ...user, password: "" })),
  };
}

function isPublished(entity) {
  return entity.status === "published";
}

function canAccessByPolicy(policy, tariffId) {
  if (!policy?.tariffIds?.length) {
    return true;
  }
  return Boolean(tariffId && policy.tariffIds.includes(tariffId));
}

function isExpired(user) {
  return Boolean(user?.expiresAt && Date.parse(user.expiresAt) < Date.now());
}

function getLessonsForModule(state, moduleId) {
  return [...state.lessons]
    .filter((lesson) => lesson.moduleId === moduleId && lesson.status !== "archived")
    .sort((left, right) => left.order - right.order);
}

function previousLesson(state, lesson) {
  const lessons = getLessonsForModule(state, lesson.moduleId);
  const index = lessons.findIndex((item) => item.id === lesson.id);
  return index > 0 ? lessons[index - 1] : undefined;
}

function lessonCompleted(state, lessonId, studentId) {
  return Boolean(
    state.progress.find((item) => item.lessonId === lessonId && item.studentId === studentId)?.isCompleted,
  );
}

function accessResult(state, entity, user) {
  if (!user) {
    return { allowed: false, reason: "login" };
  }
  if (isExpired(user)) {
    return { allowed: false, reason: "expired" };
  }
  if (user.role !== "student") {
    return { allowed: true, reason: "ok" };
  }
  if (!isPublished(entity)) {
    return { allowed: false, reason: "unpublished" };
  }
  if (!canAccessByPolicy(entity.accessPolicy, user.tariffId)) {
    return { allowed: false, reason: "tariff" };
  }
  if (entity.moduleId && entity.accessPolicy?.sequential) {
    const prev = previousLesson(state, entity);
    if (prev && !lessonCompleted(state, prev.id, user.id)) {
      return { allowed: false, reason: "previous" };
    }
  }
  return { allowed: true, reason: "ok" };
}

function visibleByAccess(state, entity, user) {
  const access = accessResult(state, entity, user);
  return access.allowed || entity.accessPolicy?.visibility === "show_locked";
}

function redactLockedEntity(state, entity, user) {
  if (accessResult(state, entity, user).allowed) {
    return entity;
  }
  if ("videoUrl" in entity) {
    return { ...entity, videoUrl: "", blockIds: [], materialIds: [], homeworkTemplateId: null };
  }
  if ("externalUrl" in entity) {
    return { ...entity, externalUrl: undefined, itemIds: [] };
  }
  if ("materialType" in entity) {
    return { ...entity, url: undefined, body: undefined };
  }
  return entity;
}

function stateForUser(state, user) {
  const safeState = sanitizeState(state);

  if (user?.role === "admin") {
    return safeState;
  }

  if (user?.role === "manager") {
    return {
      ...safeState,
      users: safeState.users.filter((item) => item.role === "student" || item.id === user.id),
      progress: [],
    };
  }

  if (!user) {
    return {
      ...safeState,
      users: [],
      trainings: [],
      folders: [],
      modules: [],
      lessons: [],
      lessonBlocks: [],
      materials: [],
      homeworkTemplates: [],
      homeworkAnswers: [],
      progress: [],
    };
  }

  const trainings = safeState.trainings
    .filter((training) => training.status !== "archived" && visibleByAccess(state, training, user))
    .map((training) => redactLockedEntity(state, training, user));
  const trainingIds = new Set(trainings.map((training) => training.id));

  const folders = safeState.folders
    .filter(
      (folder) =>
        folder.status !== "archived" &&
        trainingIds.has(folder.trainingId) &&
        visibleByAccess(state, folder, user),
    )
    .map((folder) => redactLockedEntity(state, folder, user));
  const folderIds = new Set(folders.map((folder) => folder.id));
  const allowedFolderIds = new Set(
    state.folders
      .filter((folder) => folder.status !== "archived" && trainingIds.has(folder.trainingId))
      .filter((folder) => accessResult(state, folder, user).allowed)
      .map((folder) => folder.id),
  );

  const modules = safeState.modules
    .filter(
      (module) =>
        module.status !== "archived" &&
        trainingIds.has(module.trainingId) &&
        visibleByAccess(state, module, user),
    )
    .map((module) => redactLockedEntity(state, module, user));
  const moduleIds = new Set(modules.map((module) => module.id));

  const lessons = safeState.lessons
    .filter(
      (lesson) =>
        lesson.status !== "archived" &&
        moduleIds.has(lesson.moduleId) &&
        visibleByAccess(state, lesson, user),
    )
    .map((lesson) => redactLockedEntity(state, lesson, user));
  const allowedLessonIds = new Set(
    state.lessons
      .filter((lesson) => lesson.status !== "archived" && moduleIds.has(lesson.moduleId))
      .filter((lesson) => accessResult(state, lesson, user).allowed)
      .map((lesson) => lesson.id),
  );
  const lessonIds = new Set(lessons.map((lesson) => lesson.id));

  const materials = safeState.materials
    .filter((material) => {
      if (material.status === "archived" || !visibleByAccess(state, material, user)) {
        return false;
      }
      if (material.parentType === "folder") {
        return folderIds.has(material.parentId);
      }
      return lessonIds.has(material.parentId);
    })
    .map((material) => {
      const parentAllowed =
        material.parentType === "folder"
          ? allowedFolderIds.has(material.parentId)
          : allowedLessonIds.has(material.parentId);
      return parentAllowed ? redactLockedEntity(state, material, user) : { ...material, url: undefined, body: undefined };
    });

  return {
    ...safeState,
    users: safeState.users.filter((item) => item.id === user.id),
    trainings,
    folders,
    modules,
    lessons,
    lessonBlocks: safeState.lessonBlocks.filter((block) => allowedLessonIds.has(block.lessonId)),
    materials,
    homeworkTemplates: safeState.homeworkTemplates.filter(
      (template) => allowedLessonIds.has(template.lessonId) && template.requiredTariffIds.includes(user.tariffId),
    ),
    homeworkAnswers: safeState.homeworkAnswers.filter((answer) => answer.studentId === user.id),
    progress: safeState.progress.filter((progress) => progress.studentId === user.id),
  };
}

function getSessionUser(request, state) {
  const sessionId = parseCookies(request)[sessionCookieName];
  const session = sessionId ? sessions.get(sessionId) : undefined;
  if (!session || Date.parse(session.expiresAt || "") <= Date.now()) {
    if (sessionId) {
      sessions.delete(sessionId);
    }
    return undefined;
  }
  return state.users.find((user) => user.id === session.userId);
}

async function deleteSession(request) {
  const sessionId = parseCookies(request)[sessionCookieName];
  if (sessionId) {
    sessions.delete(sessionId);
  }
  await persistSessions();
}

async function clearAllSessions() {
  sessions.clear();
  await persistSessions();
}

function requireRole(request, response, state, allowedRoles, message) {
  const currentUser = getSessionUser(request, state);
  if (!currentUser || !allowedRoles.includes(currentUser.role)) {
    sendError(response, currentUser ? 403 : 401, message);
    return undefined;
  }
  return currentUser;
}

function canOpenLesson(state, user, lessonId) {
  const lesson = state.lessons.find((item) => item.id === lessonId);
  const module = lesson ? state.modules.find((item) => item.id === lesson.moduleId) : undefined;
  const training = module ? state.trainings.find((item) => item.id === module.trainingId) : undefined;

  if (!lesson || !module || !training) {
    return { ok: false, message: "Урок не найден" };
  }
  if (!accessResult(state, training, user).allowed) {
    return { ok: false, message: "Тренинг недоступен" };
  }
  if (!accessResult(state, module, user).allowed) {
    return { ok: false, message: "Модуль недоступен" };
  }
  if (!accessResult(state, lesson, user).allowed) {
    return { ok: false, message: "Урок недоступен" };
  }
  return { ok: true, lesson, module, training };
}

function canSubmitHomework(state, user, lessonId) {
  const lessonAccess = canOpenLesson(state, user, lessonId);
  if (!lessonAccess.ok) {
    return lessonAccess;
  }
  const template = state.homeworkTemplates.find((item) => item.id === lessonAccess.lesson.homeworkTemplateId);
  if (!template) {
    return { ok: false, message: "Домашка для урока не включена" };
  }
  if (!template.requiredTariffIds.includes(user.tariffId)) {
    return { ok: false, message: "Домашка недоступна на вашем тарифе" };
  }
  return { ok: true, lesson: lessonAccess.lesson, template };
}

async function readBody(request, maxBytes = 5 * 1024 * 1024) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > maxBytes) {
      throw new Error("Request body is too large");
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

async function readJsonBody(request) {
  const body = await readBody(request);
  if (body.length === 0) {
    return {};
  }
  return JSON.parse(body.toString("utf8"));
}

async function mutateState(mutator) {
  const task = writeQueue.then(async () => {
    const currentState = await readState();
    const nextState = await mutator(currentState);
    await writeState(nextState);
    return nextState;
  });
  writeQueue = task.catch(() => {});
  return task;
}

async function migrateLegacyPassword(userId, plainPassword) {
  const hashedPassword = hashPassword(plainPassword);
  await mutateState((currentState) => ({
    ...currentState,
    users: currentState.users.map((item) =>
      item.id === userId && item.password === plainPassword ? { ...item, password: hashedPassword } : item,
    ),
  }));
}

function buildStoredFilename(originalName) {
  const extension = extname(originalName).slice(0, 16);
  return `${Date.now()}-${randomUUID()}${extension}`;
}

function resolveSafeFilePath(baseDir, relativePath) {
  const cleanedPath = String(relativePath || "").replace(/^[/\\]+/, "");
  const targetPath = resolve(baseDir, cleanedPath);
  const basePrefix = baseDir.endsWith(sep) ? baseDir : `${baseDir}${sep}`;
  if (targetPath !== baseDir && !targetPath.startsWith(basePrefix)) {
    return undefined;
  }
  return targetPath;
}

function guessContentType(pathname) {
  const extension = extname(pathname).toLowerCase();
  if (extension === ".png") {
    return "image/png";
  }
  if (extension === ".jpg" || extension === ".jpeg") {
    return "image/jpeg";
  }
  if (extension === ".webp") {
    return "image/webp";
  }
  if (extension === ".gif") {
    return "image/gif";
  }
  if (extension === ".svg") {
    return "image/svg+xml";
  }
  if (extension === ".avif") {
    return "image/avif";
  }
  return "application/octet-stream";
}

async function readFormData(request, url, maxBytes = 50 * 1024 * 1024) {
  const body = await readBody(request, maxBytes);
  const headers = new Headers();
  for (const [key, value] of Object.entries(request.headers)) {
    if (Array.isArray(value)) {
      headers.set(key, value.join(", "));
    } else if (value !== undefined) {
      headers.set(key, value);
    }
  }
  const formRequest = new Request(url, {
    method: "POST",
    headers,
    body,
  });
  return formRequest.formData();
}

function redirectForRole(user) {
  if (user.role === "admin") {
    return "/admin";
  }
  if (user.role === "manager") {
    return "/manager/homeworks";
  }
  return "/trainings";
}

async function updateCollection(state, key, item) {
  const collection = state[key];
  const index = collection.findIndex((entry) => entry.id === item.id);
  let nextItem =
    key === "users" && index >= 0 && !item.password
      ? { ...item, password: collection[index].password }
      : item;
  if (key === "users" && nextItem.password && !isHashedPassword(nextItem.password)) {
    nextItem = { ...nextItem, password: hashPassword(nextItem.password) };
  }
  return {
    ...state,
    [key]: index >= 0
      ? collection.map((entry) => (entry.id === nextItem.id ? nextItem : entry))
      : [...collection, nextItem],
  };
}

function archiveInCollection(state, key, id) {
  return {
    ...state,
    [key]: state[key].map((entry) =>
      entry.id === id && "status" in entry ? { ...entry, status: "archived" } : entry,
    ),
  };
}

async function handleUpload(request, response) {
  const state = await readState();
  const currentUser = getSessionUser(request, state);
  if (!currentUser || currentUser.role !== "student") {
    sendError(response, 403, "Загрузка доступна только ученику");
    return;
  }

  const form = await readFormData(request, "http://localhost/api/homework-files");
  const files = form.getAll("files");
  const attachments = [];

  await mkdir(uploadDir, { recursive: true });

  for (const file of files) {
    if (!file || typeof file !== "object" || typeof file.arrayBuffer !== "function") {
      continue;
    }
    const originalName = String(file.name || "attachment");
    const storedName = buildStoredFilename(originalName);
    const buffer = Buffer.from(await file.arrayBuffer());
    await writeFile(join(uploadDir, storedName), buffer);
    attachments.push({
      name: originalName,
      size: buffer.length,
      type: file.type || "application/octet-stream",
      url: `/uploads/${storedName}`,
    });
    uploadOwners.set(`/uploads/${storedName}`, currentUser.id);
  }

  sendJson(response, 200, { ok: true, attachments });
}

async function handleCoverUpload(request, response) {
  const state = await readState();
  const currentUser = requireRole(request, response, state, ["admin"], "Загрузка обложек доступна только админу");
  if (!currentUser) {
    return;
  }

  const form = await readFormData(request, "http://localhost/api/cover-files");
  const files = [...form.getAll("files"), ...form.getAll("file")];
  const uploadedFiles = [];

  await mkdir(coverUploadDir, { recursive: true });

  for (const file of files) {
    if (!file || typeof file !== "object" || typeof file.arrayBuffer !== "function") {
      continue;
    }
    if (!String(file.type || "").startsWith("image/")) {
      sendError(response, 400, "Можно загружать только изображения");
      return;
    }
    const originalName = String(file.name || "cover");
    const storedName = buildStoredFilename(originalName);
    const buffer = Buffer.from(await file.arrayBuffer());
    await writeFile(join(coverUploadDir, storedName), buffer);
    uploadedFiles.push({
      name: originalName,
      size: buffer.length,
      type: file.type || "application/octet-stream",
      url: `/uploads/covers/${storedName}`,
    });
  }

  if (uploadedFiles.length === 0) {
    sendError(response, 400, "Не удалось прочитать изображения");
    return;
  }

  sendJson(response, 200, {
    ok: true,
    files: uploadedFiles,
    coverImage: uploadedFiles[0].url,
  });
}

async function serveCoverUpload(response, pathname) {
  const relativePath = decodeURIComponent(pathname.replace(/^\/uploads\/covers\//, ""));
  const targetPath = resolveSafeFilePath(coverUploadDir, relativePath);
  if (!targetPath) {
    sendError(response, 400, "Некорректный путь файла");
    return;
  }

  const stream = createReadStream(targetPath);
  stream.on("error", () => sendError(response, 404, "Файл не найден"));
  response.writeHead(200, { "content-type": guessContentType(targetPath) });
  stream.pipe(response);
}

async function serveUpload(request, response, pathname) {
  const state = await readState();
  const currentUser = getSessionUser(request, state);
  if (!currentUser) {
    sendError(response, 401, "Нужно войти");
    return;
  }

  const relativePath = decodeURIComponent(pathname.replace(/^\/uploads\//, ""));
  const publicUrl = `/uploads/${relativePath}`;
  const knownAnswer = state.homeworkAnswers.find((answer) =>
    answer.attachments.some((attachment) => attachment.url === publicUrl),
  );
  const pendingOwnerId = uploadOwners.get(publicUrl);
  const canDownload =
    currentUser.role === "admin" ||
    currentUser.role === "manager" ||
    knownAnswer?.studentId === currentUser.id ||
    pendingOwnerId === currentUser.id;
  if (!canDownload) {
    sendError(response, 403, "Файл недоступен");
    return;
  }

  const targetPath = resolveSafeFilePath(uploadDir, relativePath);
  if (!targetPath || targetPath.startsWith(`${coverUploadDir}${sep}`) || targetPath === coverUploadDir) {
    sendError(response, 400, "Некорректный путь файла");
    return;
  }

  const stream = createReadStream(targetPath);
  stream.on("error", () => sendError(response, 404, "Файл не найден"));
  response.writeHead(200, { "content-type": "application/octet-stream" });
  stream.pipe(response);
}

async function handleApi(request, response) {
  const url = new URL(request.url || "/", "http://localhost");
  const { pathname } = url;

  if (request.method === "OPTIONS") {
    response.writeHead(204);
    response.end();
    return;
  }

  if (pathname === "/api/health" && request.method === "GET") {
    sendJson(response, 200, { ok: true });
    return;
  }

  if (pathname === "/api/state" && request.method === "GET") {
    const state = await readState();
    const user = getSessionUser(request, state);
    sendJson(response, 200, { ok: true, state: stateForUser(state, user) });
    return;
  }

  if (pathname === "/api/bootstrap" && request.method === "GET") {
    const state = await readState();
    const user = getSessionUser(request, state);
    sendJson(response, 200, {
      ok: true,
      state: stateForUser(state, user),
      session: { userId: user?.id || null },
    });
    return;
  }

  if (pathname === "/api/session" && request.method === "GET") {
    const state = await readState();
    const user = getSessionUser(request, state);
    sendJson(response, 200, { ok: true, session: { userId: user?.id || null } });
    return;
  }

  if (pathname === "/api/login" && request.method === "POST") {
    const body = await readJsonBody(request);
    const state = await readState();
    const email = String(body.email || "").trim().toLowerCase();
    const password = String(body.password || "");
    const user = state.users.find((item) => item.email.trim().toLowerCase() === email);
    const passwordMatches = user ? verifyPassword(password, user.password) : false;
    if (user && passwordMatches && !isHashedPassword(user.password)) {
      await migrateLegacyPassword(user.id, user.password);
    }
    if (!user || !passwordMatches) {
      sendJson(response, 401, {
        ok: false,
        message: "Не удалось войти. Проверьте логин и пароль.",
      });
      return;
    }
    sendJson(
      response,
      200,
      {
        ok: true,
        message: "Готово",
        session: { userId: user.id },
        redirectTo: redirectForRole(user),
      },
      { "set-cookie": await createSessionCookie(user.id) },
    );
    return;
  }

  if (pathname === "/api/logout" && request.method === "POST") {
    await deleteSession(request);
    sendJson(response, 200, { ok: true, session: { userId: null } }, { "set-cookie": clearSessionCookie() });
    return;
  }

  if (pathname === "/api/reset" && request.method === "POST") {
    const currentState = await readState();
    if (!requireRole(request, response, currentState, ["admin"], "Сброс данных доступен только админу")) {
      return;
    }
    uploadOwners.clear();
    await clearAllSessions();
    const state = await resetStateFile();
    sendJson(
      response,
      200,
      { ok: true, state: stateForUser(state, undefined), session: { userId: null } },
      { "set-cookie": clearSessionCookie() },
    );
    return;
  }

  if (pathname === "/api/homework-files" && request.method === "POST") {
    await handleUpload(request, response);
    return;
  }

  if (pathname === "/api/cover-files" && request.method === "POST") {
    await handleCoverUpload(request, response);
    return;
  }

  if (pathname === "/api/homework" && request.method === "POST") {
    const state = await readState();
    const currentUser = getSessionUser(request, state);
    if (!currentUser || currentUser.role !== "student") {
      sendError(response, 403, "Отправка домашки доступна только ученику");
      return;
    }
    const body = await readJsonBody(request);
    const lessonId = String(body.lessonId || "");
    const text = String(body.text || "");
    const attachments = Array.isArray(body.attachments) ? body.attachments : [];
    const homeworkAccess = canSubmitHomework(state, currentUser, lessonId);
    if (!homeworkAccess.ok) {
      sendError(response, 403, homeworkAccess.message);
      return;
    }
    const nextState = await mutateState((currentState) => {
      const existing = currentState.homeworkAnswers.find(
        (item) => item.lessonId === lessonId && item.studentId === currentUser.id,
      );
      const now = new Date().toISOString();
      const nextAnswer = existing
        ? {
            ...existing,
            text,
            attachments: attachments.length > 0 ? attachments : existing.attachments,
            status: "submitted",
            submittedAt: existing.submittedAt || now,
            updatedAt: now,
          }
        : {
            id: `hw-${lessonId}-${currentUser.id}`,
            lessonId,
            studentId: currentUser.id,
            text,
            attachments,
            status: "submitted",
            reviewerComment: "",
            submittedAt: now,
            updatedAt: now,
            reviewerId: null,
          };
      return {
        ...currentState,
        homeworkAnswers: existing
          ? currentState.homeworkAnswers.map((item) => (item.id === existing.id ? nextAnswer : item))
          : [...currentState.homeworkAnswers, nextAnswer],
      };
    });
    sendJson(response, 200, { ok: true, state: stateForUser(nextState, currentUser) });
    return;
  }

  if (pathname === "/api/homework/review" && request.method === "POST") {
    const state = await readState();
    const currentUser = getSessionUser(request, state);
    if (!currentUser || (currentUser.role !== "manager" && currentUser.role !== "admin")) {
      sendError(response, 403, "Проверка доступна менеджеру или админу");
      return;
    }
    const body = await readJsonBody(request);
    const nextState = await mutateState((currentState) => ({
      ...currentState,
      homeworkAnswers: currentState.homeworkAnswers.map((item) =>
        item.id === body.answerId
          ? {
              ...item,
              status: body.status,
              reviewerComment: String(body.comment || ""),
              reviewerId: currentUser.id,
              updatedAt: new Date().toISOString(),
            }
          : item,
      ),
    }));
    sendJson(response, 200, { ok: true, state: stateForUser(nextState, currentUser) });
    return;
  }

  if (pathname === "/api/progress" && request.method === "POST") {
    const state = await readState();
    const currentUser = getSessionUser(request, state);
    if (!currentUser) {
      sendError(response, 401, "Нужно войти");
      return;
    }
    const body = await readJsonBody(request);
    const lessonId = String(body.lessonId || "");
    const payload = body.payload || {};
    if (currentUser.role !== "student") {
      sendError(response, 403, "Прогресс просмотра сохраняется только для ученика");
      return;
    }
    const lessonAccess = canOpenLesson(state, currentUser, lessonId);
    if (!lessonAccess.ok) {
      sendError(response, 403, lessonAccess.message);
      return;
    }
    const nextState = await mutateState((currentState) => {
      const existing = currentState.progress.find(
        (item) => item.lessonId === lessonId && item.studentId === currentUser.id,
      );
      const nextProgress = {
        id: existing?.id || `progress-${lessonId}-${currentUser.id}`,
        lessonId,
        studentId: currentUser.id,
        watchedSeconds: payload.watchedSeconds ?? existing?.watchedSeconds ?? 0,
        durationSeconds: payload.durationSeconds ?? existing?.durationSeconds ?? 0,
        lastPositionSeconds: payload.lastPositionSeconds ?? existing?.lastPositionSeconds ?? 0,
        isCompleted: payload.isCompleted ?? existing?.isCompleted ?? false,
        updatedAt: new Date().toISOString(),
      };
      return {
        ...currentState,
        progress: existing
          ? currentState.progress.map((item) => (item.id === existing.id ? nextProgress : item))
          : [...currentState.progress, nextProgress],
      };
    });
    sendJson(response, 200, { ok: true, state: stateForUser(nextState, currentUser) });
    return;
  }

  const entityMatch = pathname.match(/^\/api\/entities\/([^/]+)$/);
  if (entityMatch && request.method === "PUT") {
    const key = entityMatch[1];
    if (!entityKeys.has(key)) {
      sendError(response, 404, "Неизвестная коллекция");
      return;
    }
    const body = await readJsonBody(request);
    const currentState = await readState();
    const currentUser = requireRole(request, response, currentState, ["admin"], "Редактирование доступно только админу");
    if (!currentUser) {
      return;
    }
    const state = await mutateState((nextState) => updateCollection(nextState, key, body.item));
    sendJson(response, 200, { ok: true, state: stateForUser(state, currentUser) });
    return;
  }

  const archiveMatch = pathname.match(/^\/api\/entities\/([^/]+)\/([^/]+)\/archive$/);
  if (archiveMatch && request.method === "POST") {
    const [, key, id] = archiveMatch;
    if (!entityKeys.has(key)) {
      sendError(response, 404, "Неизвестная коллекция");
      return;
    }
    const currentState = await readState();
    const currentUser = requireRole(request, response, currentState, ["admin"], "Архивация доступна только админу");
    if (!currentUser) {
      return;
    }
    const state = await mutateState((nextState) => archiveInCollection(nextState, key, id));
    sendJson(response, 200, { ok: true, state: stateForUser(state, currentUser) });
    return;
  }

  sendError(response, 404, "API route not found");
}

await ensureDataFiles();
await loadSessionStore();

http
  .createServer((request, response) => {
    const url = new URL(request.url || "/", "http://localhost");
    if (url.pathname.startsWith("/uploads/covers/")) {
      serveCoverUpload(response, url.pathname).catch((error) => {
        console.error(error);
        sendError(response, 500, "Server error");
      });
      return;
    }
    if (url.pathname.startsWith("/uploads/")) {
      serveUpload(request, response, url.pathname).catch((error) => {
        console.error(error);
        sendError(response, 500, "Server error");
      });
      return;
    }
    handleApi(request, response).catch((error) => {
      console.error(error);
      sendError(response, 500, "Server error");
    });
  })
  .listen(port, "127.0.0.1", () => {
    console.log(`API server: http://127.0.0.1:${port}`);
  });
