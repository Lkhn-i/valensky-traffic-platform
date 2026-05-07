import type {
  AppState,
  HomeworkAnswer,
  HomeworkAttachment,
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
  | "homeworkAnswers"
  | "progress"
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

function jsonRequest(method: string, body?: unknown): RequestInit {
  return {
    method,
    credentials: "include",
    headers: {
      "content-type": "application/json",
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
  const data = await requestJson<BootstrapPayload>("/api/reset", jsonRequest("POST"));
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
): Promise<AppState> {
  const data = await requestJson<StatePayload>("/api/progress", jsonRequest("POST", { lessonId, payload }));
  return data.state;
}

export async function uploadHomeworkFilesRequest(files: File[]): Promise<HomeworkAttachment[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await fetch("/api/homework-files", {
    method: "POST",
    credentials: "include",
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
