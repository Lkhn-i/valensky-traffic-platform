import type {
  AppState,
  HomeworkAnswer,
  HomeworkAttachment,
  LessonPlayback,
  LessonProgress,
  LoginResult,
  Session,
} from "./types";

export type EntityKey = keyof Pick<
  AppState,
  | "tariffs"
  | "users"
  | "trainings"
  | "folders"
  | "modules"
  | "lessons"
  | "lessonBlocks"
  | "materials"
  | "homeworkTemplates"
>;

export type EntityValue<K extends EntityKey> = AppState[K][number];

interface StatePayload {
  ok: boolean;
  state: AppState;
}

interface SessionPayload {
  ok: boolean;
  session: Session;
}

interface BootstrapPayload extends StatePayload, SessionPayload {}

interface UploadPayload {
  ok: boolean;
  attachments: HomeworkAttachment[];
  message?: string;
}

interface UploadedCoverFile {
  name: string;
  size: number;
  type: string;
  url: string;
}

interface CoverUploadPayload {
  ok: boolean;
  files?: UploadedCoverFile[];
  coverImage?: string;
  message?: string;
}

export interface UploadedMaterialFile {
  name: string;
  size: number;
  type: string;
  url: string;
}

interface MaterialUploadPayload {
  ok: boolean;
  files?: UploadedMaterialFile[];
  materialFile?: UploadedMaterialFile;
  message?: string;
}

interface LessonPlaybackPayload {
  ok: boolean;
  playback: LessonPlayback;
}

export interface RobokassaCheckoutInput {
  tariffId: string;
  name: string;
  email: string;
  phone: string;
  contactNote?: string;
  acceptedLegal: boolean;
  acceptedMarketing?: boolean;
}

export interface RobokassaCheckoutPayload {
  ok: boolean;
  payment: {
    action: string;
    method: "POST";
    fields: Record<string, string>;
  };
  order: {
    invId: string;
    tariffTitle: string;
    amount: string;
    isTest: boolean;
  };
}

export interface RobokassaPaymentStatusPayload {
  ok: boolean;
  order: {
    status: "pending" | "paid" | "failed";
    tariffTitle: string;
    amount: string;
    customerEmail: string;
    paidAt: string | null;
  };
  delivery: {
    status: "sent" | "outbox";
    channel: string;
    deliveredAt: string;
    message?: string;
    messageId?: string;
  } | null;
  session: {
    signedIn: boolean;
    userId: string | null;
  };
  access: {
    login: string;
    password: string | null;
    passwordRevealUntil: string | null;
    loginUrl: string;
  } | null;
}

function readCookie(name: string) {
  if (typeof document === "undefined") {
    return "";
  }
  const prefix = `${name}=`;
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return match ? match.slice(prefix.length) : "";
}

function csrfHeaders(): Record<string, string> {
  let token = "";
  try {
    token = decodeURIComponent(readCookie("chalk_csrf"));
  } catch {
    token = "";
  }
  return token ? { "x-csrf-token": token } : {};
}

function jsonRequest(method: string, body?: unknown): RequestInit {
  return {
    method,
    credentials: "include",
    headers: {
      "content-type": "application/json",
      ...csrfHeaders(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    ...init,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof data.message === "string" ? data.message : "API request failed");
  }
  return data as T;
}

export async function fetchBootstrap(): Promise<{ state: AppState; session: Session }> {
  const data = await requestJson<BootstrapPayload>("/api/bootstrap");
  return { state: data.state, session: data.session };
}

export async function fetchServerState(): Promise<AppState> {
  const data = await requestJson<StatePayload>("/api/state");
  return data.state;
}

export async function loginRequest(email: string, password: string): Promise<LoginResult & { session?: Session }> {
  const response = await fetch("/api/login", jsonRequest("POST", { email, password }));
  const data = (await response.json().catch(() => ({
    ok: false,
    message: "Не удалось войти. Проверьте логин и пароль.",
  }))) as LoginResult & { session?: Session };
  return data;
}

export async function logoutRequest(): Promise<Session> {
  const data = await requestJson<SessionPayload>("/api/logout", jsonRequest("POST"));
  return data.session;
}

export async function resetServerState(): Promise<{ state: AppState; session: Session }> {
  const data = await requestJson<BootstrapPayload>(
    "/api/reset",
    jsonRequest("POST", { confirmation: "RESET_DEMO_DATA" }),
  );
  return { state: data.state, session: data.session };
}

export async function saveEntityRequest<K extends EntityKey>(key: K, item: EntityValue<K>): Promise<AppState> {
  const data = await requestJson<StatePayload>(`/api/entities/${key}`, jsonRequest("PUT", { item }));
  return data.state;
}

export async function archiveEntityRequest<K extends EntityKey>(key: K, id: string): Promise<AppState> {
  const data = await requestJson<StatePayload>(`/api/entities/${key}/${id}/archive`, jsonRequest("POST"));
  return data.state;
}

export async function submitHomeworkRequest(
  lessonId: string,
  text: string,
  attachments: HomeworkAttachment[],
): Promise<AppState> {
  const data = await requestJson<StatePayload>("/api/homework", jsonRequest("POST", { lessonId, text, attachments }));
  return data.state;
}

export async function reviewHomeworkRequest(
  answerId: string,
  status: HomeworkAnswer["status"],
  comment: string,
): Promise<AppState> {
  const data = await requestJson<StatePayload>(
    "/api/homework/review",
    jsonRequest("POST", { answerId, status, comment }),
  );
  return data.state;
}

export async function saveProgressRequest(
  lessonId: string,
  payload: Partial<LessonProgress>,
  playbackToken: string,
): Promise<AppState> {
  const data = await requestJson<StatePayload>("/api/progress", jsonRequest("POST", { lessonId, payload, playbackToken }));
  return data.state;
}

export async function fetchLessonPlaybackRequest(lessonId: string): Promise<LessonPlayback> {
  const data = await requestJson<LessonPlaybackPayload>(`/api/lessons/${encodeURIComponent(lessonId)}/playback`);
  return data.playback;
}

export async function createRobokassaCheckoutRequest(
  input: RobokassaCheckoutInput,
): Promise<RobokassaCheckoutPayload> {
  return requestJson<RobokassaCheckoutPayload>("/api/payments/robokassa/checkout", jsonRequest("POST", input));
}

export async function fetchRobokassaPaymentStatus(
  search: string,
): Promise<RobokassaPaymentStatusPayload> {
  return requestJson<RobokassaPaymentStatusPayload>(`/api/payments/robokassa/status${search || ""}`);
}

export async function uploadHomeworkFilesRequest(files: File[]): Promise<HomeworkAttachment[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await fetch("/api/homework-files", {
    method: "POST",
    credentials: "include",
    headers: csrfHeaders(),
    body: formData,
  });
  const data = (await response.json().catch(() => ({
    ok: false,
    message: "Не удалось загрузить файлы.",
    attachments: [],
  }))) as UploadPayload;

  if (!response.ok) {
    throw new Error(data.message || "Не удалось загрузить файлы.");
  }

  return data.attachments;
}

export async function uploadCoverImageRequest(file: File): Promise<string> {
  const formData = new FormData();
  formData.append("files", file);

  const response = await fetch("/api/cover-files", {
    method: "POST",
    credentials: "include",
    headers: csrfHeaders(),
    body: formData,
  });
  const data = (await response.json().catch(() => ({
    ok: false,
    message: "Не удалось загрузить обложку.",
  }))) as CoverUploadPayload;

  if (!response.ok) {
    throw new Error(data.message || "Не удалось загрузить обложку.");
  }

  const coverImage = data.coverImage || data.files?.[0]?.url;
  if (!coverImage) {
    throw new Error("Сервер не вернул URL обложки.");
  }

  return coverImage;
}

export async function uploadMaterialFileRequest(file: File): Promise<UploadedMaterialFile> {
  const formData = new FormData();
  formData.append("files", file);

  const response = await fetch("/api/material-files", {
    method: "POST",
    credentials: "include",
    headers: csrfHeaders(),
    body: formData,
  });
  const data = (await response.json().catch(() => ({
    ok: false,
    message: "Не удалось загрузить файл материала.",
  }))) as MaterialUploadPayload;

  if (!response.ok) {
    throw new Error(data.message || "Не удалось загрузить файл материала.");
  }

  const materialFile = data.materialFile || data.files?.[0];
  if (!materialFile?.url) {
    throw new Error("Сервер не вернул URL файла материала.");
  }

  return materialFile;
}
