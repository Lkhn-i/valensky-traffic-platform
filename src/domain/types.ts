export type PublishStatus = "draft" | "published" | "archived";
export type TariffId = "workshop" | "basic" | "mentor" | "vip";
export type Role = "student" | "manager" | "admin";
export type FolderKind = "folder" | "external";
export type MaterialType = "link" | "file" | "text" | "template" | "prompt" | "embed";
export type LessonBlockType = "text" | "checklist" | "quote" | "cta";
export type HomeworkStatus =
  | "not_submitted"
  | "submitted"
  | "in_review"
  | "accepted"
  | "revision";
export type AccessReason =
  | "ok"
  | "login"
  | "tariff"
  | "expired"
  | "unpublished"
  | "previous";

export interface AccessPolicy {
  tariffIds: TariffId[];
  visibility: "show_locked" | "hide";
  sequential: boolean;
  durationMode: "rolling" | "fixed" | "lifetime";
  durationDays: number | null;
  note: string;
}

export interface BaseEntity {
  id: string;
  title: string;
  description: string;
  order: number;
  status: PublishStatus;
  accessPolicy: AccessPolicy;
  coverStyle: string;
  coverImage?: string;
}

export interface Tariff {
  id: TariffId;
  title: string;
  priceLabel: string;
  tagline: string;
  accessWindow: string;
  features: string[];
  highlight: string;
  sortOrder: number;
}

export interface User {
  id: string;
  role: Role;
  name: string;
  email: string;
  password: string;
  bio: string;
  tariffId?: TariffId;
  expiresAt?: string | null;
  trainingGrantIds: string[];
}

export interface Training extends BaseEntity {
  subtitle: string;
  tagline: string;
  folderIds: string[];
  moduleIds: string[];
}

export interface Folder extends BaseEntity {
  trainingId: string;
  parentFolderId: string | null;
  kind: FolderKind;
  externalUrl?: string;
  itemIds: string[];
}

export interface Module extends BaseEntity {
  trainingId: string;
  lessonIds: string[];
}

export interface Lesson extends BaseEntity {
  moduleId: string;
  summary: string;
  durationMinutes: number;
  videoUrl: string;
  blockIds: string[];
  materialIds: string[];
  homeworkTemplateId: string | null;
}

export interface Material extends BaseEntity {
  parentType: "folder" | "lesson";
  parentId: string;
  materialType: MaterialType;
  url?: string;
  body?: string;
  metaLabel?: string;
}

export interface LessonBlock {
  id: string;
  lessonId: string;
  type: LessonBlockType;
  title: string;
  body: string;
  bullets: string[];
  order: number;
  coverImage?: string;
  status?: PublishStatus;
}

export interface HomeworkTemplate {
  id: string;
  lessonId: string;
  title: string;
  prompt: string;
  checklist: string[];
  requiredTariffIds: TariffId[];
}

export interface HomeworkAttachment {
  name: string;
  size: number;
  type: string;
  url?: string;
}

export interface HomeworkAnswer {
  id: string;
  lessonId: string;
  studentId: string;
  text: string;
  attachments: HomeworkAttachment[];
  status: HomeworkStatus;
  reviewerComment: string;
  submittedAt: string | null;
  updatedAt: string;
  reviewerId: string | null;
}

export interface LessonProgress {
  id: string;
  lessonId: string;
  studentId: string;
  watchedSeconds: number;
  durationSeconds: number;
  lastPositionSeconds: number;
  isCompleted: boolean;
  updatedAt: string;
}

export interface Session {
  userId: string | null;
}

export interface AccessResult {
  allowed: boolean;
  reason: AccessReason;
  message: string;
}

export interface AppState {
  tariffs: Tariff[];
  users: User[];
  trainings: Training[];
  folders: Folder[];
  modules: Module[];
  lessons: Lesson[];
  lessonBlocks: LessonBlock[];
  materials: Material[];
  homeworkTemplates: HomeworkTemplate[];
  homeworkAnswers: HomeworkAnswer[];
  progress: LessonProgress[];
}

export interface LoginResult {
  ok: boolean;
  message: string;
  redirectTo?: string;
}
