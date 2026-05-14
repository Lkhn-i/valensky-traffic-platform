import { createReadStream, createWriteStream, existsSync, readFileSync } from "node:fs";
import { mkdir, rename, stat, unlink, writeFile } from "node:fs/promises";
import http from "node:http";
import { extname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import {
  createHash,
  createHmac,
  randomBytes,
  randomInt,
  randomUUID,
  scryptSync,
  timingSafeEqual,
} from "node:crypto";
import Busboy from "busboy";
import nodemailer from "nodemailer";
import { createAccessPasswordCodec } from "./access-secrets.mjs";
import { SqliteDocumentStore } from "./sqlite-document-store.mjs";
import {
  readJsonFile,
  restoreLatestStateBackup,
  withPreservedLocalUploadReferences,
  writeJsonFile,
} from "./state-protection.mjs";

const rootDir = join(fileURLToPath(new URL(".", import.meta.url)), "..");
loadEnvFile(join(rootDir, ".env"));
const dataDir = join(rootDir, "server", "data");
const uploadDir = join(rootDir, "server", "uploads");
const coverUploadDir = join(uploadDir, "covers");
const materialUploadDir = join(uploadDir, "materials");
const seedPath = join(dataDir, "seed-state.json");
const statePath = join(dataDir, "app-state.json");
const stateBackupDir = join(dataDir, "backups");
const sessionStorePath = join(dataDir, "session-store.json");
const paymentOrdersPath = join(dataDir, "payment-orders.json");
const accessOutboxPath = join(dataDir, "access-outbox.json");
const sqliteDbPath = process.env.APP_SQLITE_PATH || join(dataDir, "app.sqlite");
const sqliteBinPath = process.env.APP_SQLITE_BIN || "sqlite3";
const storageDriver = (process.env.APP_STORAGE_DRIVER || "sqlite").toLowerCase();
const sessionCookieName = "chalk_session";
const csrfCookieName = "chalk_csrf";
const sessionMaxAgeSeconds = 60 * 60 * 24 * 30;
const passwordHashPrefix = "scrypt";
const port = Number(process.env.API_PORT || 8787);
const isProduction = process.env.NODE_ENV === "production" || process.env.APP_ENV === "production";
const allowDemoAccounts = process.env.ALLOW_DEMO_ACCOUNTS === "true";
const defaultKinescopeDrmJwtSecret = "local-dev-kinescope-secret-change-me";
const kinescopeEmbedBaseUrl = process.env.KINESCOPE_EMBED_BASE_URL || "https://kinescope.io/embed";
const kinescopeDrmJwtSecret = process.env.KINESCOPE_DRM_JWT_SECRET || defaultKinescopeDrmJwtSecret;
const kinescopeDrmIssuer = process.env.KINESCOPE_DRM_ISSUER || "chalk-learning-platform";
const kinescopeDrmAudience = process.env.KINESCOPE_DRM_AUDIENCE || "kinescope-drm";
const kinescopeDrmTokenTtlSeconds = Number(process.env.KINESCOPE_DRM_TOKEN_TTL_SECONDS || 15 * 60);
const kinescopeDrmAuthUser = process.env.KINESCOPE_DRM_AUTH_USER || "";
const kinescopeDrmAuthPassword = process.env.KINESCOPE_DRM_AUTH_PASSWORD || "";
const sessionCookieSecure =
  process.env.SESSION_COOKIE_SECURE === undefined ? isProduction : process.env.SESSION_COOKIE_SECURE === "true";
const publicBaseUrl = (process.env.PUBLIC_BASE_URL || (isProduction ? "https://valenskytraffic.ru" : "http://127.0.0.1:4173")).replace(/\/+$/, "");
const defaultAllowedOrigins = isProduction
  ? publicBaseUrl
  : "http://127.0.0.1:4173,http://localhost:4173,http://127.0.0.1:8787,http://localhost:8787";
const allowedOrigins = new Set(
  (process.env.APP_ALLOWED_ORIGINS || defaultAllowedOrigins)
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
);
const loginRateLimitWindowMs = 15 * 60 * 1000;
const loginRateLimitMaxAttempts = Number(process.env.LOGIN_RATE_LIMIT_MAX_ATTEMPTS || 8);
const loginRateLimitStore = new Map();
const apiRateLimitWindowMs = Number(process.env.API_RATE_LIMIT_WINDOW_MS || 60 * 1000);
const apiRateLimitMaxRequests = Number(process.env.API_RATE_LIMIT_MAX_REQUESTS || 240);
const uploadRateLimitWindowMs = Number(process.env.UPLOAD_RATE_LIMIT_WINDOW_MS || 10 * 60 * 1000);
const uploadRateLimitMaxRequests = Number(process.env.UPLOAD_RATE_LIMIT_MAX_REQUESTS || 20);
const paymentRateLimitWindowMs = Number(process.env.PAYMENT_RATE_LIMIT_WINDOW_MS || 10 * 60 * 1000);
const paymentRateLimitMaxRequests = Number(process.env.PAYMENT_RATE_LIMIT_MAX_REQUESTS || 30);
const apiRateLimitStore = new Map();
const uploadRateLimitStore = new Map();
const paymentRateLimitStore = new Map();
const playbackSessionTtlMs = 4 * 60 * 60 * 1000;
const playbackProgressSlackSeconds = 20;
const playbackProgressRateMultiplier = 1.25;
const playbackSessions = new Map();
const requiredPaymentLegalDocuments = ["offer", "terms", "privacy", "personalDataConsent"];
const marketingLegalDocuments = ["marketingConsent"];
const lessonCompletionAcknowledgementText =
  "Подтверждаю, что изучил(а) урок, материалы открылись корректно, содержание урока понятно, а при вопросах я обращусь в поддержку.";
const coverMaxBytes = 10 * 1024 * 1024;
const materialMaxBytes = 200 * 1024 * 1024;
const homeworkMaxBytes = 50 * 1024 * 1024;
const maxUploadFiles = 10;
const robokassaPaymentUrl = process.env.ROBOKASSA_PAYMENT_URL || "https://auth.robokassa.ru/Merchant/Index.aspx";
const robokassaMerchantLogin = process.env.ROBOKASSA_MERCHANT_LOGIN || "";
const robokassaHashAlgorithm = (process.env.ROBOKASSA_HASH_ALGORITHM || "md5").toLowerCase();
const robokassaTestMode = process.env.ROBOKASSA_TEST_MODE === undefined ? true : process.env.ROBOKASSA_TEST_MODE === "true";
const robokassaPassword1 = process.env.ROBOKASSA_PASSWORD1 || "";
const robokassaPassword2 = process.env.ROBOKASSA_PASSWORD2 || "";
const robokassaTestPassword1 = process.env.ROBOKASSA_TEST_PASSWORD1 || "";
const robokassaTestPassword2 = process.env.ROBOKASSA_TEST_PASSWORD2 || "";
const robokassaReceiptEnabled = process.env.ROBOKASSA_RECEIPT_ENABLED === "true";
const robokassaDefaultTax = process.env.ROBOKASSA_TAX || "none";
const accessPasswordSecret = process.env.ACCESS_PASSWORD_SECRET || (isProduction ? "" : "local-dev-access-password-secret");
const accessPasswordRevealTtlMs = Number(process.env.ACCESS_PASSWORD_REVEAL_TTL_MS || 15 * 60 * 1000);
const accessPasswordCodec = createAccessPasswordCodec(accessPasswordSecret || "missing-access-password-secret");
const accessDeliveryMode = (process.env.ACCESS_DELIVERY_MODE || "auto").toLowerCase();
const accessEmailFrom = process.env.ACCESS_EMAIL_FROM || '"Менторство Валенского" <no-reply@valenskytraffic.ru>';
const accessEmailReplyTo = process.env.ACCESS_EMAIL_REPLY_TO || "";
const smtpHost = process.env.SMTP_HOST || "";
const smtpUser = process.env.SMTP_USER || "";
const smtpPassword = process.env.SMTP_PASSWORD || "";
const smtpSecureEnv = process.env.SMTP_SECURE;
const smtpPort = Number(process.env.SMTP_PORT || (smtpSecureEnv === "true" ? 465 : 587));
const smtpSecure = smtpSecureEnv === undefined ? smtpPort === 465 : smtpSecureEnv === "true";
const smtpIgnoreTlsEnv = process.env.SMTP_IGNORE_TLS;
const smtpIsLocalPlainRelay = ["127.0.0.1", "localhost", "::1"].includes(smtpHost) && smtpPort === 25;
const smtpIgnoreTls = smtpIgnoreTlsEnv === undefined ? smtpIsLocalPlainRelay : smtpIgnoreTlsEnv === "true";
const sendmailPath = process.env.SENDMAIL_PATH || "/usr/sbin/sendmail";
const accessEmailRetryIntervalMs = Number(process.env.ACCESS_EMAIL_RETRY_INTERVAL_MS || 10 * 60 * 1000);
const allowedCoverExtensions = new Set([".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"]);
const allowedMaterialExtensions = new Set([
  ".pdf",
  ".txt",
  ".md",
  ".doc",
  ".docx",
  ".xls",
  ".xlsx",
  ".ppt",
  ".pptx",
  ".zip",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".gif",
  ".mp4",
  ".mov",
  ".m4v",
  ".webm",
]);
const fallbackStudentStartAt = "2026-05-07T00:00:00.000Z";
const hourMs = 60 * 60 * 1000;
let writeQueue = Promise.resolve();
let sessionWriteQueue = Promise.resolve();
let paymentWriteQueue = Promise.resolve();
let accessOutboxWriteQueue = Promise.resolve();
let storageReady = null;
let sqliteStore = null;
const sessions = new Map();
const uploadOwners = new Map();
const accessDeliveryInFlight = new Set();

function loadEnvFile(filePath) {
  if (!existsSync(filePath)) {
    return;
  }
  const lines = readFileSync(filePath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) {
      continue;
    }
    const [key, ...valueParts] = trimmed.split("=");
    if (!key || process.env[key] !== undefined) {
      continue;
    }
    process.env[key] = valueParts.join("=").replace(/^["']|["']$/g, "");
  }
}

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
]);

const securityHeaders = {
  "x-content-type-options": "nosniff",
  "referrer-policy": "no-referrer",
  "x-frame-options": "DENY",
  "content-security-policy": "default-src 'none'; frame-ancestors 'self'",
};

function withSecurityHeaders(headers = {}) {
  return {
    ...securityHeaders,
    ...headers,
  };
}

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function sendJson(response, status, payload, headers = {}) {
  response.writeHead(status, {
    ...withSecurityHeaders({ "content-type": "application/json; charset=utf-8", ...headers }),
  });
  response.end(JSON.stringify(payload));
}

function sendError(response, status, message) {
  sendJson(response, status, { ok: false, message });
}

function sendCaughtError(response, error) {
  if (response.headersSent) {
    response.destroy(error);
    return;
  }
  if (error instanceof HttpError) {
    sendError(response, error.status, error.message);
    return;
  }
  console.error(error);
  sendError(response, 500, "Server error");
}

function base64UrlEncode(value) {
  const buffer = Buffer.isBuffer(value) ? value : Buffer.from(String(value));
  return buffer.toString("base64url");
}

function signJwt(payload, secret) {
  const header = { alg: "HS256", typ: "JWT" };
  const encodedHeader = base64UrlEncode(JSON.stringify(header));
  const encodedPayload = base64UrlEncode(JSON.stringify(payload));
  const signature = createHmac("sha256", secret)
    .update(`${encodedHeader}.${encodedPayload}`)
    .digest("base64url");
  return `${encodedHeader}.${encodedPayload}.${signature}`;
}

function verifyJwt(token, secret) {
  const [encodedHeader, encodedPayload, signature] = String(token || "").split(".");
  if (!encodedHeader || !encodedPayload || !signature) {
    return undefined;
  }
  const expectedSignature = createHmac("sha256", secret)
    .update(`${encodedHeader}.${encodedPayload}`)
    .digest("base64url");
  const actual = Buffer.from(signature);
  const expected = Buffer.from(expectedSignature);
  if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) {
    return undefined;
  }
  try {
    const payload = JSON.parse(Buffer.from(encodedPayload, "base64url").toString("utf8"));
    if (payload.exp && Number(payload.exp) < Math.floor(Date.now() / 1000)) {
      return undefined;
    }
    return payload;
  } catch {
    return undefined;
  }
}

function safeEqualString(left, right) {
  const leftBuffer = Buffer.from(String(left || ""));
  const rightBuffer = Buffer.from(String(right || ""));
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

function prunePlaybackSessions() {
  const now = Date.now();
  for (const [sessionId, session] of playbackSessions) {
    if (!session?.expiresAtMs || session.expiresAtMs <= now) {
      playbackSessions.delete(sessionId);
    }
  }
}

function createPlaybackToken(state, lesson, user) {
  prunePlaybackSessions();
  const sessionId = randomUUID();
  const existingProgress = state.progress.find((item) => item.lessonId === lesson.id && item.studentId === user.id);
  const fallbackDuration = Math.max(0, Number(lesson.durationMinutes || 0) * 60);
  const now = Date.now();
  playbackSessions.set(sessionId, {
    userId: user.id,
    lessonId: lesson.id,
    issuedAtMs: now,
    expiresAtMs: now + playbackSessionTtlMs,
    baselineWatchedSeconds: Math.max(0, Number(existingProgress?.watchedSeconds || 0)),
    maxCreditedSeconds: Math.max(0, Number(existingProgress?.watchedSeconds || 0)),
    durationSeconds: Math.max(0, Number(existingProgress?.durationSeconds || fallbackDuration)),
  });
  return signJwt(
    {
      typ: "lesson-playback-progress",
      jti: sessionId,
      sub: user.id,
      lessonId: lesson.id,
      iat: Math.floor(now / 1000),
      exp: Math.floor((now + playbackSessionTtlMs) / 1000),
    },
    kinescopeDrmJwtSecret,
  );
}

function getPlaybackSession(token, user, lessonId) {
  const payload = verifyJwt(token, kinescopeDrmJwtSecret);
  if (
    !payload ||
    payload.typ !== "lesson-playback-progress" ||
    payload.sub !== user.id ||
    payload.lessonId !== lessonId
  ) {
    return undefined;
  }
  const session = playbackSessions.get(payload.jti);
  if (!session || session.userId !== user.id || session.lessonId !== lessonId || session.expiresAtMs <= Date.now()) {
    return undefined;
  }
  return session;
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

function createCsrfToken() {
  return randomBytes(32).toString("base64url");
}

function csrfCookieValue(request) {
  const value = String(parseCookies(request)[csrfCookieName] || "");
  return /^[a-zA-Z0-9_-]{32,256}$/.test(value) ? value : "";
}

function createCsrfCookie(token) {
  const secureFlag = sessionCookieSecure ? "; Secure" : "";
  return `${csrfCookieName}=${encodeURIComponent(token)}; Path=/; SameSite=Lax; Max-Age=${sessionMaxAgeSeconds}${secureFlag}`;
}

function ensureCsrfCookie(request) {
  const existingToken = csrfCookieValue(request);
  if (existingToken) {
    return { token: existingToken, cookie: "" };
  }
  const token = createCsrfToken();
  return { token, cookie: createCsrfCookie(token) };
}

function appendSetCookie(headers, cookie) {
  if (!cookie) {
    return headers;
  }
  const current = headers["set-cookie"];
  if (!current) {
    return { ...headers, "set-cookie": cookie };
  }
  return {
    ...headers,
    "set-cookie": Array.isArray(current) ? [...current, cookie] : [current, cookie],
  };
}

function withCsrfCookie(request, headers = {}) {
  return appendSetCookie(headers, ensureCsrfCookie(request).cookie);
}

function getRequestOrigin(request) {
  const origin = String(request.headers.origin || "").trim();
  if (origin) {
    return origin;
  }
  const referer = String(request.headers.referer || "").trim();
  if (!referer) {
    return "";
  }
  try {
    return new URL(referer).origin;
  } catch {
    return "";
  }
}

function isStateChangingMethod(method) {
  return method !== "GET" && method !== "HEAD" && method !== "OPTIONS";
}

function validateCsrfRequest(request) {
  if (!isStateChangingMethod(request.method || "GET")) {
    return { ok: true };
  }
  const pathname = new URL(request.url || "/", "http://localhost").pathname;
  if (pathname === "/api/kinescope/drm-auth" || pathname === "/api/payments/robokassa/result") {
    return { ok: true };
  }
  const origin = getRequestOrigin(request);
  if (!origin) {
    return isProduction
      ? { ok: false, message: "Запрос отклонен: не удалось проверить источник." }
      : { ok: true };
  }
  if (!allowedOrigins.has(origin)) {
    return { ok: false, message: "Запрос отклонен: источник не разрешен." };
  }
  const cookieToken = csrfCookieValue(request);
  const headerToken = String(request.headers["x-csrf-token"] || "").trim();
  if (!cookieToken || !headerToken || !safeEqualString(cookieToken, headerToken)) {
    return { ok: false, message: "Запрос отклонен: защитный токен устарел. Обновите страницу." };
  }
  return { ok: true };
}

function getClientIp(request) {
  const forwardedFor = String(request.headers["x-forwarded-for"] || "").split(",")[0].trim();
  return forwardedFor || request.socket?.remoteAddress || "unknown";
}

function checkFixedWindowRateLimit(store, key, windowMs, maxRequests) {
  const now = Date.now();
  const entry = store.get(key);
  if (!entry || entry.resetAt <= now) {
    store.set(key, { count: 1, resetAt: now + windowMs });
    return { blocked: false, remainingMs: windowMs };
  }
  const nextCount = entry.count + 1;
  store.set(key, { count: nextCount, resetAt: entry.resetAt });
  return {
    blocked: nextCount > maxRequests,
    remainingMs: Math.max(0, entry.resetAt - now),
  };
}

function rateLimitProfile(pathname) {
  if (pathname === "/api/health") {
    return undefined;
  }
  if (pathname === "/api/login") {
    return { store: apiRateLimitStore, windowMs: apiRateLimitWindowMs, maxRequests: apiRateLimitMaxRequests, scope: "api" };
  }
  if (pathname === "/api/homework-files" || pathname === "/api/cover-files" || pathname === "/api/material-files") {
    return {
      store: uploadRateLimitStore,
      windowMs: uploadRateLimitWindowMs,
      maxRequests: uploadRateLimitMaxRequests,
      scope: "upload",
    };
  }
  if (pathname.startsWith("/api/payments/")) {
    return {
      store: paymentRateLimitStore,
      windowMs: paymentRateLimitWindowMs,
      maxRequests: paymentRateLimitMaxRequests,
      scope: "payment",
    };
  }
  if (pathname.startsWith("/api/")) {
    return { store: apiRateLimitStore, windowMs: apiRateLimitWindowMs, maxRequests: apiRateLimitMaxRequests, scope: "api" };
  }
  return undefined;
}

function enforceRateLimit(request, response, pathname) {
  const profile = rateLimitProfile(pathname);
  if (!profile) {
    return true;
  }
  const key = `${profile.scope}:${getClientIp(request)}`;
  const result = checkFixedWindowRateLimit(profile.store, key, profile.windowMs, profile.maxRequests);
  if (!result.blocked) {
    return true;
  }
  const retrySeconds = Math.max(1, Math.ceil(result.remainingMs / 1000));
  response.writeHead(429, withSecurityHeaders({ "content-type": "application/json; charset=utf-8", "retry-after": String(retrySeconds) }));
  response.end(JSON.stringify({ ok: false, message: `Слишком много запросов. Повторите через ${retrySeconds} сек.` }));
  return false;
}

function loginRateLimitKey(request, email) {
  return `${getClientIp(request)}:${String(email || "").toLowerCase()}`;
}

function getLoginRateLimit(request, email) {
  const key = loginRateLimitKey(request, email);
  const now = Date.now();
  const entry = loginRateLimitStore.get(key);
  if (!entry || entry.resetAt <= now) {
    return { key, blocked: false, remainingMs: 0 };
  }
  if (entry.count >= loginRateLimitMaxAttempts) {
    return { key, blocked: true, remainingMs: entry.resetAt - now };
  }
  return { key, blocked: false, remainingMs: entry.resetAt - now };
}

function recordLoginFailure(key) {
  const now = Date.now();
  const entry = loginRateLimitStore.get(key);
  if (!entry || entry.resetAt <= now) {
    loginRateLimitStore.set(key, { count: 1, resetAt: now + loginRateLimitWindowMs });
    return;
  }
  loginRateLimitStore.set(key, { count: entry.count + 1, resetAt: entry.resetAt });
}

function resetLoginFailures(key) {
  loginRateLimitStore.delete(key);
}

function isHashedPassword(value) {
  return typeof value === "string" && value.startsWith(`${passwordHashPrefix}$`);
}

function hashPassword(password) {
  const salt = randomBytes(16).toString("hex");
  const hash = scryptSync(password, salt, 64).toString("hex");
  return `${passwordHashPrefix}$${salt}$${hash}`;
}

function encryptAccessPassword(password) {
  return accessPasswordCodec.encrypt(password);
}

function decryptAccessPassword(encryptedPassword) {
  return accessPasswordCodec.decrypt(encryptedPassword);
}

function orderAccessPassword(order) {
  if (order?.accessPasswordEncrypted) {
    return decryptAccessPassword(order.accessPasswordEncrypted);
  }
  return typeof order?.accessPassword === "string" ? order.accessPassword : "";
}

function canRevealAccessPassword(order) {
  const revealUntilMs = Date.parse(order?.accessPasswordRevealUntil || "");
  return Number.isFinite(revealUntilMs) && revealUntilMs > Date.now();
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
  await writeDocument("sessions", sessionStorePath, serializeSessions());
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
  sessions.clear();
  const payload = await readDocument("sessions", sessionStorePath, { sessions: [] });
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
  const secureFlag = sessionCookieSecure ? "; Secure" : "";
  return `${sessionCookieName}=${encodeURIComponent(sessionId)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${sessionMaxAgeSeconds}${secureFlag}`;
}

function clearSessionCookie() {
  const secureFlag = sessionCookieSecure ? "; Secure" : "";
  return `${sessionCookieName}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${secureFlag}`;
}

function assertProductionConfig() {
  if (!isProduction) {
    return;
  }
  if (!process.env.KINESCOPE_DRM_JWT_SECRET || kinescopeDrmJwtSecret === defaultKinescopeDrmJwtSecret) {
    throw new Error("KINESCOPE_DRM_JWT_SECRET must be set to a private production secret.");
  }
  if (!kinescopeDrmAuthUser || !kinescopeDrmAuthPassword) {
    throw new Error("KINESCOPE_DRM_AUTH_USER and KINESCOPE_DRM_AUTH_PASSWORD are required in production.");
  }
  if (allowedOrigins.size === 0) {
    throw new Error("APP_ALLOWED_ORIGINS must contain at least one production origin.");
  }
  if (robokassaMerchantLogin) {
    if (robokassaTestMode && (!robokassaTestPassword1 || !robokassaTestPassword2)) {
      throw new Error("ROBOKASSA_TEST_PASSWORD1 and ROBOKASSA_TEST_PASSWORD2 are required while test payments are enabled.");
    }
    if (!robokassaTestMode && (!robokassaPassword1 || !robokassaPassword2)) {
      throw new Error("ROBOKASSA_PASSWORD1 and ROBOKASSA_PASSWORD2 are required while production payments are enabled.");
    }
  }
  if (!accessPasswordSecret) {
    throw new Error("ACCESS_PASSWORD_SECRET must be set in production.");
  }
}

function assertProductionStateSafe(state) {
  if (!isProduction) {
    return;
  }
  const unsafeUser = state.users.find((user) => {
    const email = String(user.email || "").toLowerCase();
    return email.endsWith("@example.com") || !isHashedPassword(user.password);
  });
  if (unsafeUser) {
    if (allowDemoAccounts) {
      console.warn(`Production state still contains demo or unhashed user credentials: ${unsafeUser.email || unsafeUser.id}`);
      return;
    }
    throw new Error(`Production state contains demo or unhashed user credentials: ${unsafeUser.email || unsafeUser.id}`);
  }
}

async function readLegacyJson(path, fallback) {
  return readJsonFile(path).catch(() => fallback);
}

function isSqliteStorage() {
  return storageDriver === "sqlite";
}

function safeBackupReason(reason) {
  return String(reason || "state")
    .toLowerCase()
    .replace(/[^a-z0-9а-яё-]+/gi, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60) || "state";
}

function backupTimestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

async function backupCurrentState(reason = "state") {
  await mkdir(stateBackupDir, { recursive: true });
  const backupPath = join(stateBackupDir, `${backupTimestamp()}-${safeBackupReason(reason)}.json`);
  await writeJsonFile(backupPath, await readState());
  return backupPath;
}

async function ensureBaseDataDirectories() {
  await mkdir(dataDir, { recursive: true });
  await mkdir(stateBackupDir, { recursive: true });
  await mkdir(uploadDir, { recursive: true });
  await mkdir(coverUploadDir, { recursive: true });
  await mkdir(materialUploadDir, { recursive: true });
  try {
    await stat(seedPath);
  } catch {
    throw new Error("Seed data is missing. Run `npm run seed:export` before starting the API server.");
  }
}

async function initialStateDocument() {
  const existingState = await readLegacyJson(statePath, undefined);
  if (existingState) {
    return existingState;
  }
  const restoredBackup = await restoreLatestStateBackup(statePath, stateBackupDir);
  if (restoredBackup) {
    return readJsonFile(statePath);
  }
  return readJsonFile(seedPath);
}

async function initializeSqliteStorage() {
  sqliteStore = new SqliteDocumentStore({ dbPath: sqliteDbPath, sqlitePath: sqliteBinPath });
  await sqliteStore.initialize();
  await sqliteStore.ensure("state", initialStateDocument);
  await sqliteStore.ensure("sessions", () => readLegacyJson(sessionStorePath, { sessions: [] }));
  await sqliteStore.ensure("paymentOrders", () => readLegacyJson(paymentOrdersPath, { orders: [] }));
  await sqliteStore.ensure("accessOutbox", () => readLegacyJson(accessOutboxPath, { messages: [] }));
}

async function initializeJsonStorage() {
  try {
    await stat(statePath);
  } catch {
    const restoredBackup = await restoreLatestStateBackup(statePath, stateBackupDir);
    if (!restoredBackup) {
      await writeJsonFile(statePath, await readJsonFile(seedPath));
    }
  }
  try {
    await stat(sessionStorePath);
  } catch {
    await writeFile(sessionStorePath, `${JSON.stringify({ sessions: [] }, null, 2)}\n`);
  }
  try {
    await stat(paymentOrdersPath);
  } catch {
    await writeFile(paymentOrdersPath, `${JSON.stringify({ orders: [] }, null, 2)}\n`);
  }
  try {
    await stat(accessOutboxPath);
  } catch {
    await writeFile(accessOutboxPath, `${JSON.stringify({ messages: [] }, null, 2)}\n`, { mode: 0o600 });
  }
}

async function ensureDataFiles() {
  if (!storageReady) {
    storageReady = (async () => {
      await ensureBaseDataDirectories();
      if (isSqliteStorage()) {
        await initializeSqliteStorage();
        return;
      }
      await initializeJsonStorage();
    })();
  }
  return storageReady;
}

async function readDocument(key, jsonPath, fallback) {
  await ensureDataFiles();
  const fallbackValue = typeof fallback === "function" ? await fallback() : fallback;
  if (isSqliteStorage()) {
    return sqliteStore.read(key, fallbackValue);
  }
  return readJsonFile(jsonPath).catch(() => fallbackValue);
}

async function writeDocument(key, jsonPath, value, options = {}) {
  await ensureDataFiles();
  if (isSqliteStorage()) {
    await sqliteStore.write(key, value);
    return;
  }
  const tempPath = `${jsonPath}.${randomUUID()}.tmp`;
  await writeFile(tempPath, `${JSON.stringify(value, null, 2)}\n`, options);
  await rename(tempPath, jsonPath);
}

async function readState() {
  return normalizeState(await readDocument("state", statePath, () => readJsonFile(seedPath)));
}

async function writeState(state) {
  await writeDocument("state", statePath, normalizeState(state));
}

async function readPaymentOrders() {
  const payload = await readDocument("paymentOrders", paymentOrdersPath, { orders: [] });
  return {
    orders: Array.isArray(payload.orders) ? payload.orders : [],
  };
}

async function writePaymentOrders(payload) {
  await writeDocument("paymentOrders", paymentOrdersPath, { orders: payload.orders || [] });
}

async function readAccessOutbox() {
  const payload = await readDocument("accessOutbox", accessOutboxPath, { messages: [] });
  return {
    messages: Array.isArray(payload.messages) ? payload.messages : [],
  };
}

async function writeAccessOutbox(payload) {
  await writeDocument("accessOutbox", accessOutboxPath, { messages: payload.messages || [] }, { mode: 0o600 });
}

async function appendAccessOutbox(message) {
  const task = accessOutboxWriteQueue.then(async () => {
    const payload = await readAccessOutbox();
    await writeAccessOutbox({ messages: [...payload.messages, message] });
  });
  accessOutboxWriteQueue = task.catch(() => {});
  return task;
}

function securePaymentOrderForStorage(order, now) {
  if (!order || typeof order !== "object" || !order.accessPassword) {
    return order;
  }
  const { accessPassword, ...rest } = order;
  return {
    ...rest,
    accessPasswordEncrypted: rest.accessPasswordEncrypted || encryptAccessPassword(accessPassword),
    accessPasswordMigratedAt: rest.accessPasswordMigratedAt || now,
    updatedAt: rest.updatedAt || now,
  };
}

async function migrateStoredAccessSecrets() {
  const now = new Date().toISOString();
  await mutatePaymentOrders((payload) => ({
    orders: payload.orders.map((order) => securePaymentOrderForStorage(order, now)),
  }));

  const outboxPayload = await readAccessOutbox();
  const messages = outboxPayload.messages;
  const sanitizedMessages = messages.map(({ text, html, ...message }) => message);
  const changed = messages.some((message) => "text" in message || "html" in message);
  if (changed) {
    await writeAccessOutbox({ messages: sanitizedMessages });
  }
}

function normalizeState(state) {
  return {
    ...state,
    users: (state.users || []).map((user) => ({
      ...user,
      createdAt: user.createdAt || fallbackStudentStartAt,
    })),
    lessons: (state.lessons || []).map((lesson) => ({
      ...lesson,
      unlockDelayHours: lesson.unlockDelayHours ?? 0,
    })),
  };
}

async function resetStateFile() {
  await ensureDataFiles();
  const previousState = await readState();
  await backupCurrentState("before-reset");
  const seedState = await readJsonFile(seedPath);
  const state = await withPreservedLocalUploadReferences(seedState, previousState, {
    coverUploadDir,
    materialUploadDir,
  });
  await writeState(state);
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

function formatAccessDate(value) {
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

function formatRemainingUntil(value, nowMs = Date.now()) {
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

const stateIndexCache = new WeakMap();

function appendToIndex(index, key, item) {
  const current = index.get(key);
  if (current) {
    current.push(item);
  } else {
    index.set(key, [item]);
  }
}

function sortByOrder(left, right) {
  return left.order - right.order;
}

function progressKey(studentId, lessonId) {
  return `${studentId}:${lessonId}`;
}

function createEntityMap(items) {
  return new Map(items.map((item) => [item.id, item]));
}

function getStateIndex(state) {
  const cached = stateIndexCache.get(state);
  if (cached) {
    return cached;
  }

  const modulesByTraining = new Map();
  for (const module of state.modules) {
    if (module.status !== "archived") {
      appendToIndex(modulesByTraining, module.trainingId, module);
    }
  }

  const lessonsByModule = new Map();
  const lessonByKinescopeVideoId = new Map();
  for (const lesson of state.lessons) {
    if (lesson.status !== "archived") {
      appendToIndex(lessonsByModule, lesson.moduleId, lesson);
    }
    const videoId = String(lesson.kinescopeVideoId || "").trim();
    if (videoId) {
      lessonByKinescopeVideoId.set(videoId, lesson);
    }
  }

  const completedLessons = new Set();
  for (const progress of state.progress) {
    if (progress.isCompleted) {
      completedLessons.add(progressKey(progress.studentId, progress.lessonId));
    }
  }

  const materialsByUrl = new Map();
  for (const material of state.materials) {
    if (material.url) {
      materialsByUrl.set(material.url, material);
    }
  }

  const answerByAttachmentUrl = new Map();
  for (const answer of state.homeworkAnswers) {
    for (const attachment of answer.attachments || []) {
      if (attachment.url) {
        answerByAttachmentUrl.set(attachment.url, answer);
      }
    }
  }

  for (const modules of modulesByTraining.values()) {
    modules.sort(sortByOrder);
  }
  for (const lessons of lessonsByModule.values()) {
    lessons.sort(sortByOrder);
  }

  const index = {
    trainingsById: createEntityMap(state.trainings),
    foldersById: createEntityMap(state.folders),
    modulesById: createEntityMap(state.modules),
    lessonsById: createEntityMap(state.lessons),
    usersById: createEntityMap(state.users),
    modulesByTraining,
    lessonsByModule,
    trainingLessons: new Map(),
    completedLessons,
    materialsByUrl,
    answerByAttachmentUrl,
    lessonByKinescopeVideoId,
  };
  stateIndexCache.set(state, index);
  return index;
}

function getLessonsForModule(state, moduleId) {
  return getStateIndex(state).lessonsByModule.get(moduleId) || [];
}

function getModulesForTraining(state, trainingId) {
  return getStateIndex(state).modulesByTraining.get(trainingId) || [];
}

function getTrainingForLesson(state, lesson) {
  const index = getStateIndex(state);
  const module = index.modulesById.get(lesson.moduleId);
  if (!module) {
    return undefined;
  }
  return index.trainingsById.get(module.trainingId);
}

function getTrainingLessonsInOrder(state, trainingId) {
  const index = getStateIndex(state);
  const cached = index.trainingLessons.get(trainingId);
  if (cached) {
    return cached;
  }
  const lessons = getModulesForTraining(state, trainingId).flatMap((module) => getLessonsForModule(state, module.id));
  index.trainingLessons.set(trainingId, lessons);
  return lessons;
}

function previousLesson(state, lesson) {
  const training = getTrainingForLesson(state, lesson);
  const lessons = training ? getTrainingLessonsInOrder(state, training.id) : getLessonsForModule(state, lesson.moduleId);
  const index = lessons.findIndex((item) => item.id === lesson.id);
  return index > 0 ? lessons[index - 1] : undefined;
}

function getStudentStartMs(user) {
  const parsed = Date.parse(user?.createdAt || fallbackStudentStartAt);
  return Number.isFinite(parsed) ? parsed : Date.parse(fallbackStudentStartAt);
}

function getLessonDelayMs(lesson) {
  return Math.max(0, Number(lesson.unlockDelayHours || 0)) * hourMs;
}

function lessonUnlockInfo(state, lesson, user) {
  if (!user || user.role !== "student") {
    return { timeUnlocked: true, previousTimeUnlocked: true };
  }
  const training = getTrainingForLesson(state, lesson);
  if (!training) {
    return { timeUnlocked: true, previousTimeUnlocked: true };
  }
  const lessons = getTrainingLessonsInOrder(state, training.id);
  let unlockMs = getStudentStartMs(user);
  let previousLessonItem;
  let previousAvailableAt;
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
  return { timeUnlocked: true, previousTimeUnlocked: true };
}

function lessonCompleted(state, lessonId, studentId) {
  return getStateIndex(state).completedLessons.has(progressKey(studentId, lessonId));
}

function accessResult(state, entity, user) {
  if (!user) {
    return { allowed: false, reason: "login", message: "Нужно войти" };
  }
  if (isExpired(user)) {
    return { allowed: false, reason: "expired", message: "Доступ истек" };
  }
  if (user.role !== "student") {
    return { allowed: true, reason: "ok", message: "Доступ открыт" };
  }
  if (!isPublished(entity)) {
    return { allowed: false, reason: "unpublished", message: "Материал еще не опубликован" };
  }
  if (!canAccessByPolicy(entity.accessPolicy, user.tariffId)) {
    return { allowed: false, reason: "tariff", message: "Недоступно на вашем тарифе" };
  }
  if (entity.moduleId) {
    const unlockInfo = lessonUnlockInfo(state, entity, user);
    if (!unlockInfo.previousTimeUnlocked) {
      const title = unlockInfo.previousLesson?.title || "предыдущий урок";
      const remaining = formatRemainingUntil(unlockInfo.previousAvailableAt);
      return {
        allowed: false,
        reason: "previous_time",
        message: `Сначала по расписанию должен открыться урок «${title}»${
          unlockInfo.previousAvailableAt ? `: ${formatAccessDate(unlockInfo.previousAvailableAt)}` : ""
        }${remaining ? `, осталось ${remaining}` : ""}`,
        availableAt: unlockInfo.availableAt,
        dependsOnLessonTitle: title,
        dependsOnAvailableAt: unlockInfo.previousAvailableAt,
      };
    }
    if (!unlockInfo.timeUnlocked) {
      const remaining = formatRemainingUntil(unlockInfo.availableAt);
      return {
        allowed: false,
        reason: "time",
        message: `Откроется по расписанию: ${formatAccessDate(unlockInfo.availableAt)}${
          remaining ? `, осталось ${remaining}` : ""
        }`,
        availableAt: unlockInfo.availableAt,
        dependsOnLessonTitle: unlockInfo.previousLesson?.title,
        dependsOnAvailableAt: unlockInfo.previousAvailableAt,
      };
    }
    const prev = previousLesson(state, entity);
    if (prev && !lessonCompleted(state, prev.id, user.id)) {
      return {
        allowed: false,
        reason: "previous",
        message: `Сначала завершите предыдущий урок: «${prev.title}»`,
        dependsOnLessonTitle: prev.title,
      };
    }
  }
  return { allowed: true, reason: "ok", message: "Доступ открыт" };
}

function visibleByAccess(state, entity, user) {
  const access = accessResult(state, entity, user);
  const isZeroAccessUser = user?.role === "student" && user.tariffId === "zero";
  return access.allowed || (!isZeroAccessUser && entity.accessPolicy?.visibility === "show_locked");
}

function redactLockedEntity(state, entity, user) {
  if (accessResult(state, entity, user).allowed) {
    return entity;
  }
  if ("videoUrl" in entity) {
    return { ...entity, videoUrl: "", blockIds: [], materialIds: [], homeworkTemplateId: null, timecodes: [] };
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
  return getStateIndex(state).usersById.get(session.userId);
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
  const index = getStateIndex(state);
  const lesson = index.lessonsById.get(lessonId);
  const module = lesson ? index.modulesById.get(lesson.moduleId) : undefined;
  const training = module ? index.trainingsById.get(module.trainingId) : undefined;

  if (!lesson || !module || !training) {
    return { ok: false, message: "Урок не найден" };
  }
  const trainingAccess = accessResult(state, training, user);
  if (!trainingAccess.allowed) {
    return { ok: false, message: trainingAccess.message || "Тренинг недоступен" };
  }
  const moduleAccess = accessResult(state, module, user);
  if (!moduleAccess.allowed) {
    return { ok: false, message: moduleAccess.message || "Модуль недоступен" };
  }
  const lessonAccess = accessResult(state, lesson, user);
  if (!lessonAccess.allowed) {
    return { ok: false, message: lessonAccess.message || "Урок недоступен" };
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

function canOpenMaterial(state, user, material) {
  if (!material) {
    return { ok: false, message: "Материал не найден" };
  }
  if (!accessResult(state, material, user).allowed) {
    return { ok: false, message: "Материал недоступен" };
  }
  if (material.parentType === "lesson") {
    const lessonAccess = canOpenLesson(state, user, material.parentId);
    if (!lessonAccess.ok) {
      return lessonAccess;
    }
    return { ok: true, material, lesson: lessonAccess.lesson };
  }

  const index = getStateIndex(state);
  const folder = index.foldersById.get(material.parentId);
  const training = folder ? index.trainingsById.get(folder.trainingId) : undefined;
  if (!folder || !training) {
    return { ok: false, message: "Папка материала не найдена" };
  }
  if (!accessResult(state, training, user).allowed) {
    return { ok: false, message: "Тренинг недоступен" };
  }
  if (!accessResult(state, folder, user).allowed) {
    return { ok: false, message: "Папка недоступна" };
  }
  return { ok: true, material, folder };
}

function getLessonVideoProvider(lesson) {
  if (lesson.videoProvider === "kinescope" || lesson.kinescopeVideoId) {
    return "kinescope";
  }
  return "external";
}

function buildKinescopePlaybackUrl(lesson, user) {
  const videoId = String(lesson.kinescopeVideoId || "").trim();
  if (!videoId) {
    return undefined;
  }

  const url = new URL(`${kinescopeEmbedBaseUrl.replace(/\/$/, "")}/${encodeURIComponent(videoId)}`);
  if (lesson.kinescopePlayerId) {
    url.searchParams.set("player", lesson.kinescopePlayerId);
  }
  if (lesson.kinescopeUseDrmAuth !== false) {
    const now = Math.floor(Date.now() / 1000);
    const token = signJwt(
      {
        iss: kinescopeDrmIssuer,
        aud: kinescopeDrmAudience,
        sub: user.id,
        email: user.email,
        name: user.name,
        videoId,
        lessonId: lesson.id,
        iat: now,
        exp: now + kinescopeDrmTokenTtlSeconds,
      },
      kinescopeDrmJwtSecret,
    );
    url.searchParams.set("drmauthtoken", token);
  }
  if (lesson.kinescopeUseWatermark !== false) {
    url.searchParams.set("externalid", user.id);
    url.searchParams.set("watermark", `${user.email || user.name || user.id}`);
  }
  return url.toString();
}

function buildLessonPlayback(state, lesson, user) {
  const provider = getLessonVideoProvider(lesson);
  const playbackToken = createPlaybackToken(state, lesson, user);
  if (provider === "kinescope") {
    const embedUrl = buildKinescopePlaybackUrl(lesson, user);
    return {
      provider,
      title: lesson.title,
      durationMinutes: lesson.durationMinutes,
      playbackToken,
      embedUrl,
      videoId: lesson.kinescopeVideoId || "",
      useDrmAuth: lesson.kinescopeUseDrmAuth !== false,
      useWatermark: lesson.kinescopeUseWatermark !== false,
      message: embedUrl ? undefined : "В уроке не указан ID видео Kinescope",
    };
  }
  return {
    provider: "external",
    title: lesson.title,
    durationMinutes: lesson.durationMinutes,
    playbackToken,
    videoUrl: lesson.videoUrl || "",
  };
}

function validateKinescopeBasicAuth(request) {
  if (!kinescopeDrmAuthUser && !kinescopeDrmAuthPassword) {
    return !isProduction;
  }
  const header = String(request.headers.authorization || "");
  if (!header.toLowerCase().startsWith("basic ")) {
    return false;
  }
  const decoded = Buffer.from(header.slice(6), "base64").toString("utf8");
  const [username, ...passwordParts] = decoded.split(":");
  return safeEqualString(username, kinescopeDrmAuthUser) && safeEqualString(passwordParts.join(":"), kinescopeDrmAuthPassword);
}

function findLessonByKinescopeVideoId(state, videoId) {
  return getStateIndex(state).lessonByKinescopeVideoId.get(String(videoId || "").trim());
}

function safeProgressSeconds(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.round(number)) : 0;
}

function trustedProgressPatch(existing, session, lesson, payload) {
  const fallbackDuration = safeProgressSeconds((lesson.durationMinutes || 0) * 60);
  const durationSeconds = Math.max(
    safeProgressSeconds(payload.durationSeconds),
    safeProgressSeconds(existing?.durationSeconds),
    safeProgressSeconds(session.durationSeconds),
    fallbackDuration,
  );
  const reportedPosition = safeProgressSeconds(payload.lastPositionSeconds);
  const reportedWatched = safeProgressSeconds(payload.watchedSeconds);
  const existingWatched = safeProgressSeconds(existing?.watchedSeconds);
  const elapsedSeconds = Math.max(0, (Date.now() - session.issuedAtMs) / 1000);
  const sessionCap = session.baselineWatchedSeconds + elapsedSeconds * playbackProgressRateMultiplier + playbackProgressSlackSeconds;
  const maxReported = Math.max(reportedPosition, reportedWatched, existingWatched, safeProgressSeconds(session.maxCreditedSeconds));
  const trustedWatchedSeconds = Math.min(durationSeconds || maxReported, sessionCap, maxReported);
  const lastPositionSeconds = durationSeconds ? Math.min(reportedPosition, durationSeconds) : reportedPosition;
  const trustedCompleted =
    Boolean(payload.isCompleted) &&
    payload.completionAcknowledged === true &&
    durationSeconds > 0 &&
    trustedWatchedSeconds / durationSeconds >= 0.9 &&
    lastPositionSeconds / durationSeconds >= 0.85;
  const completionAcknowledgedAt =
    existing?.completionAcknowledgedAt ||
    (trustedCompleted ? new Date().toISOString() : null);

  session.maxCreditedSeconds = Math.max(session.maxCreditedSeconds, trustedWatchedSeconds);
  session.durationSeconds = Math.max(session.durationSeconds, durationSeconds);

  return {
    watchedSeconds: Math.max(existingWatched, trustedWatchedSeconds),
    durationSeconds,
    lastPositionSeconds,
    isCompleted: Boolean(existing?.isCompleted || trustedCompleted),
    completionAcknowledgedAt,
    completionAcknowledgementText: completionAcknowledgedAt
      ? lessonCompletionAcknowledgementText
      : existing?.completionAcknowledgementText || "",
  };
}

async function readBody(request, maxBytes = 5 * 1024 * 1024) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > maxBytes) {
      throw new HttpError(413, `Запрос слишком большой. Максимальный размер: ${Math.round(maxBytes / 1024 / 1024)} МБ`);
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

async function mutatePaymentOrders(mutator) {
  const task = paymentWriteQueue.then(async () => {
    const currentOrders = await readPaymentOrders();
    const nextOrders = await mutator(currentOrders);
    await writePaymentOrders(nextOrders);
    return nextOrders;
  });
  paymentWriteQueue = task.catch(() => {});
  return task;
}

async function readUrlEncodedBody(request) {
  const body = await readBody(request);
  return new URLSearchParams(body.toString("utf8"));
}

function searchParamsToObject(params) {
  return Object.fromEntries([...params.entries()].map(([key, value]) => [key, value]));
}

function ensureRobokassaReady() {
  if (!robokassaMerchantLogin) {
    throw new Error("ROBOKASSA_MERCHANT_LOGIN is not configured.");
  }
  const password1 = robokassaTestMode ? robokassaTestPassword1 : robokassaPassword1;
  const password2 = robokassaTestMode ? robokassaTestPassword2 : robokassaPassword2;
  if (!password1 || !password2) {
    throw new Error("Robokassa payment passwords are not configured.");
  }
}

function robokassaPassword(kind, isTest = robokassaTestMode) {
  if (kind === "password2") {
    return isTest ? robokassaTestPassword2 : robokassaPassword2;
  }
  return isTest ? robokassaTestPassword1 : robokassaPassword1;
}

function robokassaHash(value) {
  return createHash(robokassaHashAlgorithm).update(value).digest("hex");
}

function collectRobokassaShpParams(params) {
  return Object.entries(params)
    .filter(([key, value]) => key.startsWith("Shp_") && value !== undefined && value !== null && String(value) !== "")
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`);
}

function signRobokassaPayment(order, fields, receipt) {
  const password = robokassaPassword("password1", order.isTest);
  const parts = [robokassaMerchantLogin, fields.OutSum, fields.InvId];
  if (receipt) {
    parts.push(receipt);
  }
  parts.push(password, ...collectRobokassaShpParams(fields));
  return robokassaHash(parts.join(":"));
}

function verifyRobokassaCallback(params, order, passwordKind) {
  const signature = String(params.SignatureValue || "").toLowerCase();
  if (!signature) {
    return false;
  }
  const password = robokassaPassword(passwordKind, order?.isTest);
  if (!password) {
    return false;
  }
  const expected = robokassaHash(
    [params.OutSum, params.InvId, password, ...collectRobokassaShpParams(params)].join(":"),
  ).toLowerCase();
  return safeEqualString(signature, expected);
}

function priceLabelToAmount(priceLabel) {
  const normalized = String(priceLabel || "")
    .replace(/\s/g, "")
    .replace(",", ".")
    .replace(/[^\d.]/g, "");
  if (!normalized) {
    return 0;
  }
  const value = Number(normalized);
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}

function formatMoneyAmount(value) {
  return Number(value || 0).toFixed(2);
}

function normalizeCheckoutCustomer(body) {
  const name = cleanString(body.name, 200).trim();
  const email = cleanString(body.email, 320).trim().toLowerCase();
  const phone = cleanString(body.phone, 80).trim();
  const contactNote = cleanString(body.contactNote, 1000).trim();
  if (!name || !email || !phone) {
    throw new Error("Заполните имя, email и телефон.");
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw new Error("Укажите корректный email.");
  }
  if (phone.replace(/[^\d]/g, "").length < 7) {
    throw new Error("Укажите корректный телефон.");
  }
  if (body.acceptedLegal !== true) {
    throw new Error("Перед оплатой нужно принять документы и согласие на обработку данных.");
  }
  return { name, email, phone, contactNote, acceptedMarketing: body.acceptedMarketing === true };
}

function generateAccessPassword() {
  return randomBytes(9).toString("base64url");
}

function tariffExpiresAt(tariffId, paidAt) {
  const durationDaysByTariff = {
    workshop: 14,
    basic: 90,
    mentor: 180,
    vip: null,
  };
  const durationDays = durationDaysByTariff[tariffId];
  if (!durationDays) {
    return null;
  }
  return new Date(Date.parse(paidAt) + durationDays * 24 * 60 * 60 * 1000).toISOString();
}

function nextPaymentInvId(existingOrders) {
  const used = new Set(existingOrders.map((order) => String(order.invId)));
  for (let attempt = 0; attempt < 100; attempt += 1) {
    const candidate = String(randomInt(100000000, 999999999));
    if (!used.has(candidate)) {
      return candidate;
    }
  }
  throw new Error("Не удалось создать номер заказа.");
}

function buildRobokassaReceipt(order) {
  if (!robokassaReceiptEnabled) {
    return undefined;
  }
  return JSON.stringify({
    items: [
      {
        name: order.tariffTitle,
        quantity: 1,
        sum: Number(order.amount),
        tax: robokassaDefaultTax,
        payment_method: "full_payment",
        payment_object: "service",
      },
    ],
  });
}

function buildRobokassaPaymentFields(order) {
  const fields = {
    MerchantLogin: robokassaMerchantLogin,
    OutSum: order.amount,
    InvId: order.invId,
    Description: `Доступ: ${order.tariffTitle}`.slice(0, 100),
    Culture: "ru",
    Encoding: "utf-8",
    Email: order.customer.email,
    Shp_orderId: order.id,
    Shp_statusToken: order.statusToken,
    Shp_tariffId: order.tariffId,
  };
  if (order.isTest) {
    fields.IsTest = "1";
  }
  const receipt = buildRobokassaReceipt(order);
  if (receipt) {
    fields.Receipt = receipt;
  }
  return {
    ...fields,
    SignatureValue: signRobokassaPayment(order, fields, receipt),
  };
}

function publicUrl(pathname) {
  return `${publicBaseUrl}${pathname}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function buildAccessMessage(order, accessPassword) {
  const loginUrl = publicUrl("/login");
  const subject = `Доступ к платформе: ${order.tariffTitle}`;
  const text = [
    "Здравствуйте!",
    "",
    `Оплата тарифа «${order.tariffTitle}» подтверждена.`,
    "Данные для входа в личный кабинет:",
    "",
    `Ссылка: ${loginUrl}`,
    `Логин: ${order.customer.email}`,
    `Пароль: ${accessPassword}`,
    "",
    "Если письмо попало не туда или доступ не открывается, напишите в поддержку: https://t.me/valenskymanager",
  ].join("\n");
  const html = `
    <div style="font-family: Arial, sans-serif; line-height: 1.5; color: #111;">
      <p>Здравствуйте!</p>
      <p>Оплата тарифа <strong>${escapeHtml(order.tariffTitle)}</strong> подтверждена.</p>
      <p>Данные для входа в личный кабинет:</p>
      <table cellpadding="6" cellspacing="0" style="border-collapse: collapse;">
        <tr><td><strong>Ссылка</strong></td><td><a href="${escapeHtml(loginUrl)}">${escapeHtml(loginUrl)}</a></td></tr>
        <tr><td><strong>Логин</strong></td><td>${escapeHtml(order.customer.email)}</td></tr>
        <tr><td><strong>Пароль</strong></td><td>${escapeHtml(accessPassword)}</td></tr>
      </table>
      <p>Если доступ не открывается, напишите в поддержку: <a href="https://t.me/valenskymanager">https://t.me/valenskymanager</a></p>
    </div>
  `;
  return { subject, text, html, loginUrl };
}

function createAccessMailTransport() {
  if (accessDeliveryMode === "disabled" || accessDeliveryMode === "file") {
    return null;
  }
  if ((accessDeliveryMode === "auto" || accessDeliveryMode === "smtp") && smtpHost) {
    return {
      channel: "smtp",
      transport: nodemailer.createTransport({
        host: smtpHost,
        port: smtpPort,
        secure: smtpSecure,
        ignoreTLS: smtpIgnoreTls,
        auth: smtpUser || smtpPassword ? { user: smtpUser, pass: smtpPassword } : undefined,
      }),
    };
  }
  if ((accessDeliveryMode === "auto" || accessDeliveryMode === "sendmail") && existsSync(sendmailPath)) {
    return {
      channel: "sendmail",
      transport: nodemailer.createTransport({
        sendmail: true,
        newline: "unix",
        path: sendmailPath,
      }),
    };
  }
  return null;
}

async function sendAccessMessage(order, source) {
  const now = new Date().toISOString();
  const accessPassword = orderAccessPassword(order);
  if (!accessPassword) {
    await appendAccessOutbox({
      id: `outbox-${randomUUID()}`,
      orderId: order.id,
      invId: order.invId,
      to: order.customer.email,
      source,
      reason: "access-password-unavailable",
      createdAt: now,
    });
    return {
      status: "outbox",
      channel: "file",
      deliveredAt: now,
      message: "Письмо не удалось отправить: пароль доступа недоступен для расшифровки.",
    };
  }
  const message = buildAccessMessage(order, accessPassword);
  const mailTransport = createAccessMailTransport();
  if (!mailTransport) {
    await appendAccessOutbox({
      id: `outbox-${randomUUID()}`,
      orderId: order.id,
      invId: order.invId,
      to: order.customer.email,
      subject: message.subject,
      source,
      reason: "email-transport-not-configured",
      createdAt: now,
    });
    return {
      status: "outbox",
      channel: "file",
      deliveredAt: now,
      message: "SMTP/sendmail не настроен, письмо сохранено в локальный outbox на сервере.",
    };
  }

  try {
    const info = await mailTransport.transport.sendMail({
      from: accessEmailFrom,
      to: order.customer.email,
      replyTo: accessEmailReplyTo || undefined,
      subject: message.subject,
      text: message.text,
      html: message.html,
    });
    return {
      status: "sent",
      channel: mailTransport.channel,
      deliveredAt: now,
      messageId: info.messageId || "",
    };
  } catch (error) {
    await appendAccessOutbox({
      id: `outbox-${randomUUID()}`,
      orderId: order.id,
      invId: order.invId,
      to: order.customer.email,
      subject: message.subject,
      source,
      reason: "email-send-failed",
      error: error instanceof Error ? error.message : "unknown email error",
      createdAt: now,
    });
    return {
      status: "outbox",
      channel: mailTransport.channel,
      deliveredAt: now,
      message: "Письмо не удалось отправить, данные доступа сохранены в локальный outbox на сервере.",
    };
  }
}

async function deliverPaidOrderAccess(order, source) {
  if (!order || order.status !== "paid" || order.accessDelivery?.status === "sent") {
    return order;
  }
  if (accessDeliveryInFlight.has(order.id)) {
    return order;
  }
  accessDeliveryInFlight.add(order.id);
  try {
    const delivery = await sendAccessMessage(order, source);
    const updatedAt = new Date().toISOString();
    const attempts = Number(order.accessDelivery?.attempts || 0) + 1;
    const payload = await mutatePaymentOrders((currentPayload) => ({
      orders: currentPayload.orders.map((item) =>
        item.id === order.id
          ? {
              ...item,
              accessDelivery: { ...delivery, attempts },
              accessDeliveredAt: delivery.deliveredAt,
              updatedAt,
            }
          : item,
      ),
    }));
    return payload.orders.find((item) => item.id === order.id) || { ...order, accessDelivery: delivery };
  } finally {
    accessDeliveryInFlight.delete(order.id);
  }
}

function shouldRetryAccessDelivery(order) {
  return Boolean(order && order.status === "paid" && order.accessDelivery?.status !== "sent");
}

async function retryPendingAccessDeliveries(source = "access-retry") {
  const payload = await readPaymentOrders();
  const orders = payload.orders.filter(shouldRetryAccessDelivery).slice(0, 20);
  for (const order of orders) {
    await deliverPaidOrderAccess(order, source);
  }
}

function startAccessDeliveryRetryLoop() {
  if (!Number.isFinite(accessEmailRetryIntervalMs) || accessEmailRetryIntervalMs <= 0) {
    return;
  }
  void retryPendingAccessDeliveries("startup-retry").catch((error) => {
    console.error("Access email startup retry failed", error);
  });
  const timer = setInterval(() => {
    void retryPendingAccessDeliveries("scheduled-retry").catch((error) => {
      console.error("Access email scheduled retry failed", error);
    });
  }, accessEmailRetryIntervalMs);
  timer.unref?.();
}

function upsertPaidStudent(state, order, paidAt) {
  const existing = state.users.find((user) => String(user.email || "").trim().toLowerCase() === order.customer.email);
  if (existing && existing.role !== "student") {
    throw new Error("Email уже занят служебной учетной записью. Укажите другой email.");
  }
  const accessPassword = orderAccessPassword(order);
  if (!accessPassword) {
    throw new Error("Пароль доступа недоступен. Попробуйте создать заказ заново.");
  }
  const user = {
    id: existing?.id || `student-${randomUUID()}`,
    role: "student",
    name: order.customer.name,
    email: order.customer.email,
    password: hashPassword(accessPassword),
    bio: existing?.bio || "",
    createdAt: existing?.createdAt || paidAt,
    tariffId: order.tariffId,
    expiresAt: tariffExpiresAt(order.tariffId, paidAt),
    trainingGrantIds: Array.isArray(existing?.trainingGrantIds) ? existing.trainingGrantIds : [],
  };
  return {
    user,
    state: {
      ...state,
      users: existing
        ? state.users.map((item) => (item.id === existing.id ? user : item))
        : [...state.users, user],
    },
  };
}

async function createRobokassaOrder(body) {
  ensureRobokassaReady();
  const customer = normalizeCheckoutCustomer(body);
  const tariffId = cleanString(body.tariffId, 80).trim();
  if (tariffId === "zero") {
    throw new Error("Нулевой урок выдается без оплаты.");
  }
  const state = await readState();
  const existingUser = state.users.find((user) => String(user.email || "").trim().toLowerCase() === customer.email);
  if (existingUser && existingUser.role !== "student") {
    throw new Error("Этот email уже используется для служебного аккаунта. Укажите другой email.");
  }
  const tariff = state.tariffs.find((item) => item.id === tariffId);
  if (!tariff) {
    throw new Error("Тариф не найден.");
  }
  const amount = priceLabelToAmount(tariff.priceLabel);
  if (amount <= 0) {
    throw new Error("Для этого тарифа не нужна онлайн-оплата.");
  }
  const createdAt = new Date().toISOString();
  let createdOrder;
  await mutatePaymentOrders((payload) => {
    const invId = nextPaymentInvId(payload.orders);
    const accessPassword = generateAccessPassword();
    createdOrder = {
      id: `order-${randomUUID()}`,
      invId,
      status: "pending",
      provider: "robokassa",
      isTest: robokassaTestMode,
      tariffId,
      tariffTitle: tariff.title,
      amount: formatMoneyAmount(amount),
      customer,
      accessPasswordEncrypted: encryptAccessPassword(accessPassword),
      accessPasswordRevealUntil: null,
      statusToken: randomBytes(32).toString("base64url"),
      legalAcceptedAt: createdAt,
      legalDocumentsAccepted: requiredPaymentLegalDocuments,
      marketingAcceptedAt: customer.acceptedMarketing ? createdAt : null,
      marketingDocumentsAccepted: customer.acceptedMarketing ? marketingLegalDocuments : [],
      createdAt,
      updatedAt: createdAt,
      paidAt: null,
      accessUserId: null,
    };
    return { orders: [...payload.orders, createdOrder] };
  });
  return createdOrder;
}

async function markRobokassaOrderPaid(order, source) {
  if (order.status === "paid") {
    return deliverPaidOrderAccess(order, source);
  }
  const paidAt = new Date().toISOString();
  let accessUserId = order.accessUserId || null;
  const revealUntil = order.accessPasswordRevealUntil || new Date(Date.now() + accessPasswordRevealTtlMs).toISOString();
  await mutateState((currentState) => {
    const result = upsertPaidStudent(currentState, order, paidAt);
    accessUserId = result.user.id;
    return result.state;
  });
  const orders = await mutatePaymentOrders((payload) => ({
    orders: payload.orders.map((item) =>
      item.id === order.id
        ? {
            ...item,
            status: "paid",
            paidAt,
            updatedAt: paidAt,
            paidSource: source,
            accessUserId,
            accessPasswordRevealUntil: revealUntil,
          }
        : item,
    ),
  }));
  const paidOrder = orders.orders.find((item) => item.id === order.id) || order;
  return deliverPaidOrderAccess(paidOrder, source);
}

function findPaymentOrder(payload, params) {
  const invId = String(params.InvId || "");
  const orderId = String(params.Shp_orderId || "");
  return payload.orders.find((order) => String(order.invId) === invId && (!orderId || order.id === orderId));
}

function hasPaymentStatusAccess(order, params) {
  const statusToken = String(params.Shp_statusToken || params.statusToken || "").trim();
  return Boolean(order?.statusToken && statusToken && safeEqualString(order.statusToken, statusToken));
}

function validateRobokassaAmount(params, order) {
  const received = Number(String(params.OutSum || "").replace(",", "."));
  const expected = Number(order.amount);
  return Number.isFinite(received) && Math.abs(received - expected) < 0.01;
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

function normalizedExtension(originalName) {
  return extname(String(originalName || "").trim()).toLowerCase().slice(0, 16);
}

function buildStoredFilename(originalName) {
  const extension = normalizedExtension(originalName);
  return `${Date.now()}-${randomUUID()}${extension}`;
}

function cleanOriginalFilename(filename, fallback = "file") {
  return String(filename || fallback)
    .replace(/[/\\\u0000]/g, "_")
    .replace(/[\r\n]/g, " ")
    .trim()
    .slice(0, 300) || fallback;
}

function ensureAllowedFile(file, sampleBuffer, options) {
  const originalName = String(file.name || "file");
  const extension = normalizedExtension(originalName);
  if (!options.allowedExtensions.has(extension)) {
    return `Недопустимый формат файла: ${extension || "без расширения"}`;
  }
  if (Number(file.size || 0) > options.maxBytes) {
    return `Файл слишком большой. Максимальный размер: ${Math.round(options.maxBytes / 1024 / 1024)} МБ`;
  }
  if (options.kind === "cover" && !isValidCoverImage(sampleBuffer, extension)) {
    return "Файл не похож на безопасное изображение. Используйте PNG, JPG, WEBP, GIF или AVIF.";
  }
  if (options.kind !== "cover" && !isValidMaterialFile(sampleBuffer, extension)) {
    return "Файл не прошел проверку формата. Проверьте, что расширение соответствует содержимому.";
  }
  return "";
}

function isValidCoverImage(buffer, extension) {
  if (extension === ".png") {
    return buffer.length >= 8 && buffer.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  }
  if (extension === ".jpg" || extension === ".jpeg") {
    return buffer.length >= 3 && buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff;
  }
  if (extension === ".gif") {
    const header = buffer.subarray(0, 6).toString("ascii");
    return header === "GIF87a" || header === "GIF89a";
  }
  if (extension === ".webp") {
    return buffer.length >= 12 && buffer.subarray(0, 4).toString("ascii") === "RIFF" && buffer.subarray(8, 12).toString("ascii") === "WEBP";
  }
  if (extension === ".avif") {
    const brand = buffer.subarray(4, 12).toString("ascii");
    return brand.startsWith("ftyp") && (brand.includes("avif") || brand.includes("avis") || brand.includes("mif1"));
  }
  return false;
}

function isZipFile(buffer) {
  return buffer.length >= 4 && buffer[0] === 0x50 && buffer[1] === 0x4b && [0x03, 0x05, 0x07].includes(buffer[2]);
}

function isOleFile(buffer) {
  return (
    buffer.length >= 8 &&
    buffer.subarray(0, 8).equals(Buffer.from([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]))
  );
}

function isLikelyTextFile(buffer) {
  return !buffer.includes(0x00);
}

function isMp4LikeFile(buffer) {
  return buffer.length >= 12 && buffer.subarray(4, 8).toString("ascii") === "ftyp";
}

function isWebmFile(buffer) {
  return buffer.length >= 4 && buffer.subarray(0, 4).equals(Buffer.from([0x1a, 0x45, 0xdf, 0xa3]));
}

function isValidMaterialFile(buffer, extension) {
  if (extension === ".png" || extension === ".jpg" || extension === ".jpeg" || extension === ".gif" || extension === ".webp") {
    return isValidCoverImage(buffer, extension);
  }
  if (extension === ".pdf") {
    return buffer.length >= 5 && buffer.subarray(0, 5).toString("ascii") === "%PDF-";
  }
  if (extension === ".txt" || extension === ".md") {
    return isLikelyTextFile(buffer);
  }
  if (extension === ".zip" || extension === ".docx" || extension === ".xlsx" || extension === ".pptx") {
    return isZipFile(buffer);
  }
  if (extension === ".doc" || extension === ".xls" || extension === ".ppt") {
    return isOleFile(buffer);
  }
  if (extension === ".mp4" || extension === ".m4v" || extension === ".mov") {
    return isMp4LikeFile(buffer);
  }
  if (extension === ".webm") {
    return isWebmFile(buffer);
  }
  return false;
}

async function readMultipartUploads(request, options) {
  const contentType = String(request.headers["content-type"] || "");
  if (!contentType.toLowerCase().includes("multipart/form-data")) {
    throw new HttpError(400, "Ожидалась multipart-загрузка файла.");
  }

  await mkdir(options.targetDir, { recursive: true });
  const uploadedFiles = [];
  const tasks = [];
  let filesSeen = 0;
  let firstError;

  const fail = (status, message) => {
    if (!firstError) {
      firstError = new HttpError(status, message);
    }
  };

  const busboy = Busboy({
    headers: request.headers,
    limits: {
      files: options.maxFiles,
      fileSize: options.maxBytes,
      fields: 20,
      parts: options.maxFiles + 20,
    },
  });

  busboy.on("filesLimit", () => fail(400, `Можно загрузить не больше ${options.maxFiles} файлов за раз`));
  busboy.on("partsLimit", () => fail(400, "Слишком много частей в запросе загрузки."));

  busboy.on("file", (fieldName, file, info) => {
    if (fieldName !== "files" && fieldName !== "file") {
      file.resume();
      return;
    }

    filesSeen += 1;
    if (filesSeen > options.maxFiles) {
      fail(400, `Можно загрузить не больше ${options.maxFiles} файлов за раз`);
      file.resume();
      return;
    }

    const originalName = cleanOriginalFilename(info.filename, options.defaultName || "file");
    const extension = normalizedExtension(originalName);
    if (!options.allowedExtensions.has(extension)) {
      fail(400, `Недопустимый формат файла: ${extension || "без расширения"}`);
      file.resume();
      return;
    }

    const storedName = buildStoredFilename(originalName);
    const tempPath = join(options.targetDir, `${storedName}.uploading`);
    const finalPath = join(options.targetDir, storedName);
    const headChunks = [];
    const maxHeadBytes = 8192;
    let headBytes = 0;
    let size = 0;

    const meter = new Transform({
      transform(chunk, encoding, callback) {
        size += chunk.length;
        if (headBytes < maxHeadBytes) {
          const slice = chunk.subarray(0, Math.min(chunk.length, maxHeadBytes - headBytes));
          headChunks.push(Buffer.from(slice));
          headBytes += slice.length;
        }
        if (size > options.maxBytes) {
          callback(new HttpError(413, `Файл слишком большой. Максимальный размер: ${Math.round(options.maxBytes / 1024 / 1024)} МБ`));
          return;
        }
        callback(null, chunk);
      },
    });

    const task = pipeline(file, meter, createWriteStream(tempPath, { flags: "wx" }))
      .then(async () => {
        if (file.truncated || size > options.maxBytes) {
          throw new HttpError(413, `Файл слишком большой. Максимальный размер: ${Math.round(options.maxBytes / 1024 / 1024)} МБ`);
        }
        const sampleBuffer = Buffer.concat(headChunks);
        const validationError = ensureAllowedFile(
          { name: originalName, size, type: info.mimeType || "application/octet-stream" },
          sampleBuffer,
          options,
        );
        if (validationError) {
          throw new HttpError(400, validationError);
        }
        await rename(tempPath, finalPath);
        const url = `${options.publicPrefix}/${storedName}`;
        const uploadedFile = {
          name: originalName,
          size,
          type: guessContentType(storedName),
          url,
        };
        uploadedFiles.push(uploadedFile);
        if (options.ownerId) {
          uploadOwners.set(url, options.ownerId);
        }
      })
      .catch(async (error) => {
        try {
          await unlink(tempPath);
        } catch (unlinkError) {
          if (unlinkError?.code !== "ENOENT") {
            console.warn(`Не удалось удалить временный файл ${tempPath}:`, unlinkError);
          }
        }
        fail(error instanceof HttpError ? error.status : 400, error?.message || "Не удалось сохранить файл.");
      });
    tasks.push(task);
  });

  await new Promise((resolvePromise, rejectPromise) => {
    busboy.on("error", rejectPromise);
    busboy.on("finish", resolvePromise);
    request.pipe(busboy);
  });
  await Promise.all(tasks);

  if (firstError) {
    for (const uploadedFile of uploadedFiles) {
      const relativePath = decodeURIComponent(uploadedFile.url.replace(`${options.publicPrefix}/`, ""));
      const targetPath = resolveSafeFilePath(options.targetDir, relativePath);
      if (targetPath) {
        try {
          await unlink(targetPath);
        } catch (unlinkError) {
          if (unlinkError?.code !== "ENOENT") {
            console.warn(`Не удалось удалить файл после ошибки загрузки ${uploadedFile.url}:`, unlinkError);
          }
        }
      }
    }
    throw firstError;
  }
  if (filesSeen === 0 || uploadedFiles.length === 0) {
    throw new HttpError(400, "Не удалось прочитать файлы.");
  }
  return uploadedFiles;
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

function localCoverRelativePath(coverImage) {
  const prefix = "/uploads/covers/";
  const value = String(coverImage || "");
  if (!value.startsWith(prefix)) {
    return undefined;
  }
  const relativePath = decodeURIComponent(value.slice(prefix.length));
  return relativePath || undefined;
}

function stateReferencesCoverImage(state, coverImage) {
  return [...entityKeys].some((key) =>
    Array.isArray(state[key]) && state[key].some((entry) => entry?.coverImage === coverImage),
  );
}

async function deleteLocalCoverImage(coverImage) {
  const relativePath = localCoverRelativePath(coverImage);
  if (!relativePath) {
    return;
  }
  const targetPath = resolveSafeFilePath(coverUploadDir, relativePath);
  if (!targetPath || targetPath === coverUploadDir) {
    return;
  }
  try {
    await unlink(targetPath);
  } catch (error) {
    if (error?.code !== "ENOENT") {
      console.warn(`Не удалось удалить старую обложку ${coverImage}:`, error);
    }
  }
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
  if (extension === ".avif") {
    return "image/avif";
  }
  if (extension === ".pdf") {
    return "application/pdf";
  }
  if (extension === ".txt" || extension === ".md") {
    return "text/plain; charset=utf-8";
  }
  if (extension === ".zip") {
    return "application/zip";
  }
  if (extension === ".doc") {
    return "application/msword";
  }
  if (extension === ".docx") {
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  }
  if (extension === ".xls") {
    return "application/vnd.ms-excel";
  }
  if (extension === ".xlsx") {
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  }
  if (extension === ".ppt") {
    return "application/vnd.ms-powerpoint";
  }
  if (extension === ".pptx") {
    return "application/vnd.openxmlformats-officedocument.presentationml.presentation";
  }
  if (extension === ".mp4" || extension === ".m4v") {
    return "video/mp4";
  }
  if (extension === ".mov") {
    return "video/quicktime";
  }
  if (extension === ".webm") {
    return "video/webm";
  }
  return "application/octet-stream";
}

function attachmentDisposition(filename) {
  const safeName = String(filename || "material")
    .replace(/[\r\n"]/g, "")
    .trim();
  const fallbackName = safeName.replace(/[^\x20-\x7e]/g, "_") || "material";
  return `attachment; filename="${fallbackName}"; filename*=UTF-8''${encodeURIComponent(safeName || "material")}`;
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

const validStatuses = new Set(["draft", "published", "archived"]);
const validRoles = new Set(["student", "manager", "admin"]);
const validTariffIds = new Set(["zero", "workshop", "basic", "mentor", "vip"]);
const validFolderKinds = new Set(["folder", "external"]);
const validMaterialTypes = new Set(["link", "file", "text", "template", "prompt", "embed"]);
const validLessonBlockTypes = new Set(["text", "checklist", "quote", "cta"]);
const validVideoProviders = new Set(["external", "kinescope"]);
const validHomeworkStatuses = new Set(["not_submitted", "submitted", "in_review", "accepted", "revision"]);

function ensurePlainObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} должен быть объектом`);
  }
}

function cleanString(value, maxLength = 5000) {
  return String(value ?? "").replace(/\u0000/g, "").slice(0, maxLength);
}

function cleanStringArray(value, maxItems = 100, maxLength = 500) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => cleanString(item, maxLength).trim())
    .filter(Boolean)
    .slice(0, maxItems);
}

function uniqueStrings(value, maxItems = 100) {
  return [...new Set(cleanStringArray(value, maxItems))];
}

function cleanNumber(value, fallback = 0, min = 0, max = 100000) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, number));
}

function cleanId(value) {
  const id = cleanString(value, 120).trim();
  if (!/^[a-zA-Z0-9_.:-]+$/.test(id)) {
    throw new Error("Некорректный идентификатор");
  }
  return id;
}

function cleanStatus(value, fallback = "draft") {
  return validStatuses.has(value) ? value : fallback;
}

function cleanCoverImage(value) {
  const image = cleanString(value, 12000).trim();
  if (!image) {
    return undefined;
  }
  if (image.startsWith("/uploads/covers/") || image.startsWith("data:image/svg+xml")) {
    return image;
  }
  throw new Error("Обложка должна быть загруженным локальным изображением");
}

function cleanHttpUrl(value, options = {}) {
  const url = cleanString(value, 2000).trim();
  if (!url) {
    return options.required ? "" : undefined;
  }
  if (options.allowLocalUploads && url.startsWith("/uploads/materials/")) {
    return url;
  }
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.toString();
    }
  } catch {
    // fall through to a clear validation error below
  }
  throw new Error("Ссылка должна начинаться с http:// или https://");
}

function cleanAccessPolicy(policy, fallbackPolicy) {
  const source = policy && typeof policy === "object" ? policy : fallbackPolicy || {};
  return {
    tariffIds: uniqueStrings(source.tariffIds, 10).filter((id) => validTariffIds.has(id)),
    visibility: source.visibility === "hide" ? "hide" : "show_locked",
    sequential: Boolean(source.sequential),
    durationMode: ["rolling", "fixed", "lifetime"].includes(source.durationMode) ? source.durationMode : "lifetime",
    durationDays: source.durationDays === null || source.durationDays === undefined
      ? null
      : cleanNumber(source.durationDays, 0, 0, 3650),
    note: cleanString(source.note, 1000),
  };
}

function cleanBaseEntity(item, existing) {
  const fallback = existing || {};
  const base = {
    id: cleanId(item.id),
    title: cleanString(item.title || fallback.title, 300).trim(),
    description: cleanString(item.description || fallback.description, 2000),
    order: cleanNumber(item.order, fallback.order || 0, 0, 100000),
    status: cleanStatus(item.status, fallback.status || "draft"),
    accessPolicy: cleanAccessPolicy(item.accessPolicy, fallback.accessPolicy),
    coverStyle: cleanString(item.coverStyle || fallback.coverStyle || "notebook", 80),
  };
  const coverImage = cleanCoverImage(item.coverImage ?? fallback.coverImage);
  return coverImage ? { ...base, coverImage } : base;
}

function cleanTimecodes(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.slice(0, 100).map((timecode) => ({
    id: cleanId(timecode.id || `timecode-${randomUUID()}`),
    label: cleanString(timecode.label, 300).trim(),
    seconds: cleanNumber(timecode.seconds, 0, 0, 24 * 60 * 60),
    note: cleanString(timecode.note, 1000),
  }));
}

function requireEntityExists(map, id, message) {
  if (!map.has(id)) {
    throw new Error(message);
  }
}

function sanitizeEntityForSave(state, key, item, existing) {
  ensurePlainObject(item, "Запись");
  const index = getStateIndex(state);

  if (key === "tariffs") {
    const id = cleanId(item.id);
    if (!validTariffIds.has(id)) {
      throw new Error("Можно редактировать только существующие тарифы");
    }
    return {
      id,
      title: cleanString(item.title, 200).trim(),
      priceLabel: cleanString(item.priceLabel, 100),
      tagline: cleanString(item.tagline, 1000),
      accessWindow: cleanString(item.accessWindow, 500),
      features: cleanStringArray(item.features, 50, 500),
      highlight: cleanString(item.highlight, 500),
      sortOrder: cleanNumber(item.sortOrder, existing?.sortOrder || 0, 0, 1000),
    };
  }

  if (key === "users") {
    const id = cleanId(item.id);
    const role = validRoles.has(item.role) ? item.role : existing?.role || "student";
    const tariffId = item.tariffId && validTariffIds.has(item.tariffId) ? item.tariffId : undefined;
    return {
      id,
      role,
      name: cleanString(item.name, 200).trim(),
      email: cleanString(item.email, 320).trim().toLowerCase(),
      password: cleanString(item.password, 500),
      bio: cleanString(item.bio, 2000),
      createdAt: cleanString(item.createdAt || existing?.createdAt || new Date().toISOString(), 80),
      tariffId,
      expiresAt: item.expiresAt ? cleanString(item.expiresAt, 80) : null,
      trainingGrantIds: uniqueStrings(item.trainingGrantIds, 100),
    };
  }

  if (key === "trainings") {
    return {
      ...cleanBaseEntity(item, existing),
      subtitle: cleanString(item.subtitle, 500),
      tagline: cleanString(item.tagline, 1000),
      folderIds: uniqueStrings(item.folderIds, 500),
      moduleIds: uniqueStrings(item.moduleIds, 500),
    };
  }

  if (key === "folders") {
    const base = cleanBaseEntity(item, existing);
    const trainingId = cleanId(item.trainingId);
    requireEntityExists(index.trainingsById, trainingId, "Тренинг папки не найден");
    const parentFolderId = item.parentFolderId ? cleanId(item.parentFolderId) : null;
    if (parentFolderId) {
      requireEntityExists(index.foldersById, parentFolderId, "Родительская папка не найдена");
    }
    const kind = validFolderKinds.has(item.kind) ? item.kind : "folder";
    return {
      ...base,
      trainingId,
      parentFolderId,
      kind,
      externalUrl: kind === "external" ? cleanHttpUrl(item.externalUrl) : undefined,
      itemIds: uniqueStrings(item.itemIds, 500),
    };
  }

  if (key === "modules") {
    const trainingId = cleanId(item.trainingId);
    requireEntityExists(index.trainingsById, trainingId, "Тренинг модуля не найден");
    return {
      ...cleanBaseEntity(item, existing),
      trainingId,
      lessonIds: uniqueStrings(item.lessonIds, 500),
    };
  }

  if (key === "lessons") {
    const moduleId = cleanId(item.moduleId);
    requireEntityExists(index.modulesById, moduleId, "Модуль урока не найден");
    const videoProvider = validVideoProviders.has(item.videoProvider) ? item.videoProvider : "external";
    return {
      ...cleanBaseEntity(item, existing),
      moduleId,
      summary: cleanString(item.summary, 2000),
      durationMinutes: cleanNumber(item.durationMinutes, existing?.durationMinutes || 10, 1, 24 * 60),
      unlockDelayHours: cleanNumber(item.unlockDelayHours, existing?.unlockDelayHours || 0, 0, 24 * 365),
      videoUrl: videoProvider === "external" ? cleanHttpUrl(item.videoUrl, { required: true }) : cleanString(item.videoUrl, 2000),
      videoProvider,
      kinescopeVideoId: cleanString(item.kinescopeVideoId, 200).trim(),
      kinescopePlayerId: cleanString(item.kinescopePlayerId, 200).trim(),
      kinescopeUseDrmAuth: item.kinescopeUseDrmAuth !== false,
      kinescopeUseWatermark: item.kinescopeUseWatermark !== false,
      blockIds: uniqueStrings(item.blockIds, 500),
      materialIds: uniqueStrings(item.materialIds, 500),
      homeworkTemplateId: item.homeworkTemplateId ? cleanId(item.homeworkTemplateId) : null,
      timecodes: cleanTimecodes(item.timecodes),
    };
  }

  if (key === "lessonBlocks") {
    const lessonId = cleanId(item.lessonId);
    requireEntityExists(index.lessonsById, lessonId, "Урок блока не найден");
    return {
      id: cleanId(item.id),
      lessonId,
      type: validLessonBlockTypes.has(item.type) ? item.type : "text",
      title: cleanString(item.title, 300).trim(),
      body: cleanString(item.body, 10000),
      bullets: cleanStringArray(item.bullets, 200, 1000),
      order: cleanNumber(item.order, existing?.order || 0, 0, 100000),
      status: cleanStatus(item.status, existing?.status || "draft"),
      coverImage: cleanCoverImage(item.coverImage ?? existing?.coverImage),
    };
  }

  if (key === "materials") {
    const base = cleanBaseEntity(item, existing);
    const parentType = item.parentType === "folder" ? "folder" : "lesson";
    const parentId = cleanId(item.parentId);
    if (parentType === "folder") {
      requireEntityExists(index.foldersById, parentId, "Папка материала не найдена");
    } else {
      requireEntityExists(index.lessonsById, parentId, "Урок материала не найден");
    }
    const materialType = validMaterialTypes.has(item.materialType) ? item.materialType : "text";
    const url =
      materialType === "link" || materialType === "embed"
        ? cleanHttpUrl(item.url)
        : materialType === "file"
          ? cleanHttpUrl(item.url, { allowLocalUploads: true })
          : undefined;
    return {
      ...base,
      parentType,
      parentId,
      materialType,
      url,
      body: materialType === "text" || materialType === "template" || materialType === "prompt" ? cleanString(item.body, 20000) : cleanString(item.body, 20000),
      fileName: item.fileName ? cleanString(item.fileName, 300) : undefined,
      fileSize: item.fileSize === undefined ? undefined : cleanNumber(item.fileSize, 0, 0, materialMaxBytes),
      metaLabel: cleanString(item.metaLabel, 100),
    };
  }

  if (key === "homeworkTemplates") {
    const lessonId = cleanId(item.lessonId);
    requireEntityExists(index.lessonsById, lessonId, "Урок домашнего задания не найден");
    return {
      id: cleanId(item.id),
      lessonId,
      title: cleanString(item.title, 300).trim(),
      prompt: cleanString(item.prompt, 10000),
      checklist: cleanStringArray(item.checklist, 100, 1000),
      requiredTariffIds: uniqueStrings(item.requiredTariffIds, 10).filter((id) => validTariffIds.has(id)),
    };
  }

  throw new Error("Неизвестная коллекция");
}

async function updateCollection(state, key, item) {
  const collection = state[key];
  const index = collection.findIndex((entry) => entry.id === item.id);
  const existing = index >= 0 ? collection[index] : undefined;
  let nextItem = sanitizeEntityForSave(state, key, item, existing);
  if (key === "users" && existing && !nextItem.password) {
    nextItem = { ...nextItem, password: existing.password };
  }
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

function sanitizeHomeworkAttachments(attachments, currentUser, existingAnswer) {
  const existingUrls = new Set((existingAnswer?.attachments || []).map((attachment) => attachment.url).filter(Boolean));
  return (Array.isArray(attachments) ? attachments : [])
    .slice(0, maxUploadFiles)
    .map((attachment) => ({
      name: cleanString(attachment?.name, 300) || "attachment",
      size: cleanNumber(attachment?.size, 0, 0, homeworkMaxBytes),
      type: cleanString(attachment?.type, 200) || "application/octet-stream",
      url: attachment?.url ? cleanString(attachment.url, 1000) : undefined,
    }))
    .filter((attachment) => {
      if (!attachment.url) {
        return true;
      }
      const ownerId = uploadOwners.get(attachment.url);
      return ownerId === currentUser.id || existingUrls.has(attachment.url);
    });
}

async function handleUpload(request, response) {
  const state = await readState();
  const currentUser = getSessionUser(request, state);
  if (!currentUser || currentUser.role !== "student") {
    sendError(response, 403, "Загрузка доступна только ученику");
    return;
  }

  const attachments = await readMultipartUploads(request, {
    targetDir: uploadDir,
    publicPrefix: "/uploads",
    allowedExtensions: allowedMaterialExtensions,
    maxBytes: homeworkMaxBytes,
    maxFiles: maxUploadFiles,
    kind: "attachment",
    defaultName: "attachment",
    ownerId: currentUser.id,
  });

  sendJson(response, 200, { ok: true, attachments });
}

async function handleCoverUpload(request, response) {
  const state = await readState();
  const currentUser = requireRole(request, response, state, ["admin"], "Загрузка обложек доступна только админу");
  if (!currentUser) {
    return;
  }

  const uploadedFiles = await readMultipartUploads(request, {
    targetDir: coverUploadDir,
    publicPrefix: "/uploads/covers",
    allowedExtensions: allowedCoverExtensions,
    maxBytes: coverMaxBytes,
    maxFiles: maxUploadFiles,
    kind: "cover",
    defaultName: "cover",
  });

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

async function handleMaterialUpload(request, response) {
  const state = await readState();
  const currentUser = requireRole(request, response, state, ["admin"], "Загрузка материалов доступна только админу");
  if (!currentUser) {
    return;
  }

  const uploadedFiles = await readMultipartUploads(request, {
    targetDir: materialUploadDir,
    publicPrefix: "/uploads/materials",
    allowedExtensions: allowedMaterialExtensions,
    maxBytes: materialMaxBytes,
    maxFiles: maxUploadFiles,
    kind: "material",
    defaultName: "material",
  });

  if (uploadedFiles.length === 0) {
    sendError(response, 400, "Не удалось прочитать файлы материала");
    return;
  }

  sendJson(response, 200, {
    ok: true,
    files: uploadedFiles,
    materialFile: uploadedFiles[0],
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
  response.writeHead(200, withSecurityHeaders({ "content-type": guessContentType(targetPath) }));
  stream.pipe(response);
}

async function serveMaterialUpload(request, response, pathname) {
  const state = await readState();
  const currentUser = getSessionUser(request, state);
  if (!currentUser) {
    sendError(response, 401, "Нужно войти");
    return;
  }

  const relativePath = decodeURIComponent(pathname.replace(/^\/uploads\/materials\//, ""));
  const publicUrl = `/uploads/materials/${relativePath}`;
  const material = getStateIndex(state).materialsByUrl.get(publicUrl);
  const materialAccess = material ? canOpenMaterial(state, currentUser, material) : undefined;
  const canDownload = materialAccess?.ok || (currentUser.role === "admin" && !material);
  if (!canDownload) {
    sendError(response, 403, materialAccess?.message || "Файл материала недоступен");
    return;
  }

  const targetPath = resolveSafeFilePath(materialUploadDir, relativePath);
  if (!targetPath) {
    sendError(response, 400, "Некорректный путь файла");
    return;
  }

  const stream = createReadStream(targetPath);
  stream.on("error", () => sendError(response, 404, "Файл не найден"));
  response.writeHead(200, withSecurityHeaders({
    "content-type": guessContentType(targetPath),
    "content-disposition": attachmentDisposition(material?.fileName || relativePath),
  }));
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
  const knownAnswer = getStateIndex(state).answerByAttachmentUrl.get(publicUrl);
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
  if (
    !targetPath ||
    targetPath.startsWith(`${coverUploadDir}${sep}`) ||
    targetPath === coverUploadDir ||
    targetPath.startsWith(`${materialUploadDir}${sep}`) ||
    targetPath === materialUploadDir
  ) {
    sendError(response, 400, "Некорректный путь файла");
    return;
  }

  const stream = createReadStream(targetPath);
  stream.on("error", () => sendError(response, 404, "Файл не найден"));
  response.writeHead(200, withSecurityHeaders({ "content-type": "application/octet-stream" }));
  stream.pipe(response);
}

async function handleApi(request, response) {
  const url = new URL(request.url || "/", "http://localhost");
  const { pathname } = url;

  if (request.method === "OPTIONS") {
    response.writeHead(204, withSecurityHeaders());
    response.end();
    return;
  }

  if (!enforceRateLimit(request, response, pathname)) {
    return;
  }

  const csrf = validateCsrfRequest(request);
  if (!csrf.ok) {
    sendError(response, 403, csrf.message);
    return;
  }

  if (pathname === "/api/health" && request.method === "GET") {
    sendJson(response, 200, { ok: true });
    return;
  }

  if (pathname === "/api/payments/robokassa/checkout" && request.method === "POST") {
    try {
      const body = await readJsonBody(request);
      const order = await createRobokassaOrder(body);
      sendJson(response, 200, {
        ok: true,
        payment: {
          action: robokassaPaymentUrl,
          method: "POST",
          fields: buildRobokassaPaymentFields(order),
        },
        order: {
          invId: order.invId,
          tariffTitle: order.tariffTitle,
          amount: order.amount,
          isTest: order.isTest,
        },
      });
    } catch (error) {
      sendError(response, 400, error?.message || "Не удалось создать платеж.");
    }
    return;
  }

  if (pathname === "/api/payments/robokassa/result" && (request.method === "POST" || request.method === "GET")) {
    const params =
      request.method === "POST"
        ? searchParamsToObject(await readUrlEncodedBody(request))
        : searchParamsToObject(url.searchParams);
    const payload = await readPaymentOrders();
    const order = findPaymentOrder(payload, params);
    if (
      !order ||
      !validateRobokassaAmount(params, order) ||
      !verifyRobokassaCallback(params, order, "password2")
    ) {
      sendError(response, 400, "Некорректное уведомление Robokassa.");
      return;
    }
    const paidOrder = await markRobokassaOrderPaid(order, "result-url");
    response.writeHead(200, withSecurityHeaders({ "content-type": "text/plain; charset=utf-8" }));
    response.end(`OK${paidOrder.invId}`);
    return;
  }

  if (pathname === "/api/payments/robokassa/status" && request.method === "GET") {
    const params = searchParamsToObject(url.searchParams);
    const payload = await readPaymentOrders();
    const order = findPaymentOrder(payload, params);
    if (!order) {
      sendError(response, 404, "Заказ не найден.");
      return;
    }
    let currentOrder = order;
    const hasSuccessSignature = Boolean(params.SignatureValue);
    const hasStatusToken = hasPaymentStatusAccess(order, params);
    if (!hasSuccessSignature && !hasStatusToken) {
      sendError(response, 403, "Статус заказа доступен только по защищенной ссылке оплаты.");
      return;
    }
    if (hasSuccessSignature) {
      if (
        !validateRobokassaAmount(params, order) ||
        !verifyRobokassaCallback(params, order, "password1")
      ) {
        sendError(response, 400, "Не удалось подтвердить платеж.");
        return;
      }
      currentOrder = await markRobokassaOrderPaid(order, "success-url");
    } else if (currentOrder.status === "paid" && currentOrder.accessDelivery?.status !== "sent") {
      currentOrder = await deliverPaidOrderAccess(currentOrder, "status-retry");
    }
    const revealPassword =
      currentOrder.status === "paid" && canRevealAccessPassword(currentOrder)
        ? orderAccessPassword(currentOrder)
        : "";
    let responseHeaders = withCsrfCookie(request);
    let autoSignedIn = false;
    if (currentOrder.status === "paid" && currentOrder.accessUserId) {
      responseHeaders = appendSetCookie(responseHeaders, await createSessionCookie(currentOrder.accessUserId));
      autoSignedIn = true;
    }
    sendJson(response, 200, {
      ok: true,
      order: {
        status: currentOrder.status,
        tariffTitle: currentOrder.tariffTitle,
        amount: currentOrder.amount,
        customerEmail: currentOrder.customer.email,
        paidAt: currentOrder.paidAt,
      },
      delivery: currentOrder.accessDelivery || null,
      session: {
        signedIn: autoSignedIn,
        userId: autoSignedIn ? currentOrder.accessUserId : null,
      },
      access:
        currentOrder.status === "paid"
          ? {
              login: currentOrder.customer.email,
              password: revealPassword || null,
              passwordRevealUntil: currentOrder.accessPasswordRevealUntil || null,
              loginUrl: publicUrl("/trainings"),
            }
          : null,
    }, responseHeaders);
    return;
  }

  if (pathname === "/api/state" && request.method === "GET") {
    const state = await readState();
    const user = getSessionUser(request, state);
    sendJson(response, 200, { ok: true, state: stateForUser(state, user) }, withCsrfCookie(request));
    return;
  }

  if (pathname === "/api/bootstrap" && request.method === "GET") {
    const state = await readState();
    const user = getSessionUser(request, state);
    sendJson(response, 200, {
      ok: true,
      state: stateForUser(state, user),
      session: { userId: user?.id || null },
    }, withCsrfCookie(request));
    return;
  }

  if (pathname === "/api/session" && request.method === "GET") {
    const state = await readState();
    const user = getSessionUser(request, state);
    sendJson(response, 200, { ok: true, session: { userId: user?.id || null } }, withCsrfCookie(request));
    return;
  }

  if (pathname === "/api/login" && request.method === "POST") {
    const body = await readJsonBody(request);
    const state = await readState();
    const email = String(body.email || "").trim().toLowerCase();
    const password = String(body.password || "");
    const rateLimit = getLoginRateLimit(request, email);
    if (rateLimit.blocked) {
      const retryMinutes = Math.max(1, Math.ceil(rateLimit.remainingMs / 60000));
      sendJson(response, 429, {
        ok: false,
        message: `Слишком много попыток входа. Повторите через ${retryMinutes} мин.`,
      });
      return;
    }
    const user = state.users.find((item) => item.email.trim().toLowerCase() === email);
    const passwordMatches = user ? verifyPassword(password, user.password) : false;
    if (user && passwordMatches && !isHashedPassword(user.password)) {
      await migrateLegacyPassword(user.id, user.password);
    }
    if (!user || !passwordMatches) {
      recordLoginFailure(rateLimit.key);
      sendJson(response, 401, {
        ok: false,
        message: "Не удалось войти. Проверьте логин и пароль.",
      });
      return;
    }
    resetLoginFailures(rateLimit.key);
    sendJson(
      response,
      200,
      {
        ok: true,
        message: "Готово",
        session: { userId: user.id },
        redirectTo: redirectForRole(user),
      },
      withCsrfCookie(request, { "set-cookie": await createSessionCookie(user.id) }),
    );
    return;
  }

  if (pathname === "/api/logout" && request.method === "POST") {
    await deleteSession(request);
    sendJson(response, 200, { ok: true, session: { userId: null } }, { "set-cookie": clearSessionCookie() });
    return;
  }

  if (pathname === "/api/reset" && request.method === "POST") {
    const body = await readJsonBody(request);
    const currentState = await readState();
    if (!requireRole(request, response, currentState, ["admin"], "Сброс данных доступен только админу")) {
      return;
    }
    if (body?.confirmation !== "RESET_DEMO_DATA") {
      sendError(response, 400, "Для сброса нужно явное подтверждение.");
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

  if (pathname === "/api/material-files" && request.method === "POST") {
    await handleMaterialUpload(request, response);
    return;
  }

  const playbackMatch = pathname.match(/^\/api\/lessons\/([^/]+)\/playback$/);
  if (playbackMatch && request.method === "GET") {
    const state = await readState();
    const currentUser = getSessionUser(request, state);
    if (!currentUser) {
      sendError(response, 401, "Нужно войти");
      return;
    }
    const lessonId = decodeURIComponent(playbackMatch[1]);
    const lessonAccess = canOpenLesson(state, currentUser, lessonId);
    if (!lessonAccess.ok) {
      sendError(response, 403, lessonAccess.message);
      return;
    }
    sendJson(response, 200, {
      ok: true,
      playback: buildLessonPlayback(state, lessonAccess.lesson, currentUser),
    });
    return;
  }

  if (pathname === "/api/kinescope/drm-auth" && (request.method === "POST" || request.method === "GET")) {
    if (!validateKinescopeBasicAuth(request)) {
      sendError(response, 401, "Kinescope auth credentials are invalid");
      return;
    }
    const body = request.method === "POST" ? await readJsonBody(request).catch(() => ({})) : {};
    const token =
      body.token ||
      body.drmauthtoken ||
      body.drmAuthToken ||
      url.searchParams.get("token") ||
      url.searchParams.get("drmauthtoken") ||
      "";
    const videoId =
      body.videoId ||
      body.video_id ||
      body.id ||
      url.searchParams.get("videoId") ||
      url.searchParams.get("video_id") ||
      url.searchParams.get("id") ||
      "";
    const payload = verifyJwt(token, kinescopeDrmJwtSecret);
    if (
      !payload ||
      payload.iss !== kinescopeDrmIssuer ||
      payload.aud !== kinescopeDrmAudience ||
      (videoId && payload.videoId !== videoId)
    ) {
      sendError(response, 403, "Kinescope token is invalid");
      return;
    }
    const state = await readState();
    const index = getStateIndex(state);
    const user = index.usersById.get(payload.sub);
    const lesson = index.lessonsById.get(payload.lessonId) || findLessonByKinescopeVideoId(state, payload.videoId);
    if (!user || !lesson) {
      sendError(response, 403, "Kinescope access denied");
      return;
    }
    const lessonAccess = canOpenLesson(state, user, lesson.id);
    if (!lessonAccess.ok || String(lesson.kinescopeVideoId || "") !== String(payload.videoId || "")) {
      sendError(response, 403, "Kinescope access denied");
      return;
    }
    sendJson(response, 200, { ok: true, userId: user.id, externalId: user.id });
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
    const text = cleanString(body.text, 20000);
    const requestedAttachments = Array.isArray(body.attachments) ? body.attachments : [];
    const homeworkAccess = canSubmitHomework(state, currentUser, lessonId);
    if (!homeworkAccess.ok) {
      sendError(response, 403, homeworkAccess.message);
      return;
    }
    const nextState = await mutateState((currentState) => {
      const existing = currentState.homeworkAnswers.find(
        (item) => item.lessonId === lessonId && item.studentId === currentUser.id,
      );
      const attachments = sanitizeHomeworkAttachments(requestedAttachments, currentUser, existing);
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
    if (!validHomeworkStatuses.has(body.status)) {
      sendError(response, 400, "Некорректный статус домашки");
      return;
    }
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
    const playbackToken = String(body.playbackToken || payload.playbackToken || "");
    if (currentUser.role !== "student") {
      sendError(response, 403, "Прогресс просмотра сохраняется только для ученика");
      return;
    }
    const lessonAccess = canOpenLesson(state, currentUser, lessonId);
    if (!lessonAccess.ok) {
      sendError(response, 403, lessonAccess.message);
      return;
    }
    const playbackSession = getPlaybackSession(playbackToken, currentUser, lessonId);
    if (!playbackSession) {
      sendError(response, 403, "Прогресс можно сохранять только из активного защищенного просмотра урока");
      return;
    }
    const nextState = await mutateState((currentState) => {
      const existing = currentState.progress.find(
        (item) => item.lessonId === lessonId && item.studentId === currentUser.id,
      );
      const progressPatch = trustedProgressPatch(existing, playbackSession, lessonAccess.lesson, payload);
      const nextProgress = {
        id: existing?.id || `progress-${lessonId}-${currentUser.id}`,
        lessonId,
        studentId: currentUser.id,
        ...progressPatch,
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
    let coverImageToDelete;
    let state;
    try {
      state = await mutateState(async (nextState) => {
        const previousItem = Array.isArray(nextState[key])
          ? nextState[key].find((entry) => entry.id === body.item?.id)
          : undefined;
        const updatedState = await updateCollection(nextState, key, body.item);
        const previousCoverImage = previousItem?.coverImage;
        const nextCoverImage = body.item?.coverImage;
        if (
          previousCoverImage &&
          previousCoverImage !== nextCoverImage &&
          localCoverRelativePath(previousCoverImage) &&
          !stateReferencesCoverImage(updatedState, previousCoverImage)
        ) {
          coverImageToDelete = previousCoverImage;
        }
        return updatedState;
      });
    } catch (error) {
      sendError(response, 400, error?.message || "Некорректные данные");
      return;
    }
    await deleteLocalCoverImage(coverImageToDelete);
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

assertProductionConfig();
await ensureDataFiles();
await migrateStoredAccessSecrets();
await loadSessionStore();
assertProductionStateSafe(await readState());
startAccessDeliveryRetryLoop();

http
  .createServer((request, response) => {
    const url = new URL(request.url || "/", "http://localhost");
    if (url.pathname.startsWith("/uploads/covers/")) {
      serveCoverUpload(response, url.pathname).catch((error) => {
        sendCaughtError(response, error);
      });
      return;
    }
    if (url.pathname.startsWith("/uploads/materials/")) {
      serveMaterialUpload(request, response, url.pathname).catch((error) => {
        sendCaughtError(response, error);
      });
      return;
    }
    if (url.pathname.startsWith("/uploads/")) {
      serveUpload(request, response, url.pathname).catch((error) => {
        sendCaughtError(response, error);
      });
      return;
    }
    handleApi(request, response).catch((error) => {
      sendCaughtError(response, error);
    });
  })
  .listen(port, "127.0.0.1", () => {
    console.log(`API server: http://127.0.0.1:${port}`);
  });
