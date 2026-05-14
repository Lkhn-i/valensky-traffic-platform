import { copyFile, mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import { join, resolve, sep } from "node:path";

const localCoverPrefix = "/uploads/covers/";
const localMaterialPrefix = "/uploads/materials/";
const uploadReferenceCollections = ["trainings", "folders", "modules", "lessons", "lessonBlocks", "materials"];

function cloneState(state) {
  return JSON.parse(JSON.stringify(state));
}

function safeReason(reason) {
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

function isLocalUploadReference(value, prefix) {
  return typeof value === "string" && value.startsWith(prefix) && value.length > prefix.length;
}

function resolveSafeUploadPath(baseDir, publicUrl, prefix) {
  if (!isLocalUploadReference(publicUrl, prefix)) {
    return undefined;
  }
  const relativePath = decodeURIComponent(publicUrl.slice(prefix.length)).replace(/^[/\\]+/, "");
  if (!relativePath) {
    return undefined;
  }
  const targetPath = resolve(baseDir, relativePath);
  const basePrefix = baseDir.endsWith(sep) ? baseDir : `${baseDir}${sep}`;
  return targetPath === baseDir || !targetPath.startsWith(basePrefix) ? undefined : targetPath;
}

async function fileExists(path) {
  if (!path) {
    return false;
  }
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

async function localCoverExists(coverUploadDir, coverImage) {
  return fileExists(resolveSafeUploadPath(coverUploadDir, coverImage, localCoverPrefix));
}

async function localMaterialExists(materialUploadDir, materialUrl) {
  return fileExists(resolveSafeUploadPath(materialUploadDir, materialUrl, localMaterialPrefix));
}

export async function readJsonFile(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

export async function writeJsonFile(path, data) {
  await writeFile(path, `${JSON.stringify(data, null, 2)}\n`);
}

export async function backupStateFile(statePath, backupDir, reason = "state") {
  try {
    await stat(statePath);
  } catch {
    return undefined;
  }
  await mkdir(backupDir, { recursive: true });
  const backupPath = join(backupDir, `${backupTimestamp()}-${safeReason(reason)}.json`);
  await copyFile(statePath, backupPath);
  return backupPath;
}

export async function latestStateBackupPath(backupDir) {
  let entries;
  try {
    entries = await readdir(backupDir, { withFileTypes: true });
  } catch {
    return undefined;
  }
  const backups = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => entry.name)
    .sort();
  const latest = backups.at(-1);
  return latest ? join(backupDir, latest) : undefined;
}

export async function restoreLatestStateBackup(statePath, backupDir) {
  const latestBackup = await latestStateBackupPath(backupDir);
  if (!latestBackup) {
    return undefined;
  }
  await copyFile(latestBackup, statePath);
  return latestBackup;
}

export async function withPreservedLocalUploadReferences(seedState, previousState, uploadDirs) {
  if (!previousState) {
    return cloneState(seedState);
  }

  const nextState = cloneState(seedState);
  for (const key of uploadReferenceCollections) {
    const nextItems = Array.isArray(nextState[key]) ? nextState[key] : [];
    const previousItems = Array.isArray(previousState[key]) ? previousState[key] : [];
    const previousById = new Map(previousItems.map((item) => [item?.id, item]).filter(([id]) => Boolean(id)));

    for (const nextItem of nextItems) {
      const previousItem = previousById.get(nextItem?.id);
      if (!previousItem) {
        continue;
      }

      if (await localCoverExists(uploadDirs.coverUploadDir, previousItem.coverImage)) {
        nextItem.coverImage = previousItem.coverImage;
      }

      if (
        key === "materials" &&
        previousItem.materialType === "file" &&
        (await localMaterialExists(uploadDirs.materialUploadDir, previousItem.url))
      ) {
        nextItem.materialType = "file";
        nextItem.url = previousItem.url;
        nextItem.fileName = previousItem.fileName;
        nextItem.fileSize = previousItem.fileSize;
        nextItem.metaLabel = previousItem.metaLabel || "файл";
      }
    }
  }

  return nextState;
}
