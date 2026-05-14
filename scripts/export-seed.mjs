import { mkdir, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { createHash, scryptSync } from "node:crypto";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import {
  backupStateFile,
  readJsonFile,
  restoreLatestStateBackup,
  withPreservedLocalUploadReferences,
  writeJsonFile,
} from "../server/state-protection.mjs";
import { SqliteDocumentStore } from "../server/sqlite-document-store.mjs";

const rootDir = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const dataDir = join(rootDir, "server", "data");
const uploadDir = join(rootDir, "server", "uploads");
const coverUploadDir = join(uploadDir, "covers");
const materialUploadDir = join(uploadDir, "materials");
const seedPath = join(dataDir, "seed-state.json");
const statePath = join(dataDir, "app-state.json");
const stateBackupDir = join(dataDir, "backups");
const sqliteDbPath = process.env.APP_SQLITE_PATH || join(dataDir, "app.sqlite");
const sqliteBinPath = process.env.APP_SQLITE_BIN || "sqlite3";
const storageDriver = (process.env.APP_STORAGE_DRIVER || "sqlite").toLowerCase();
const shouldReset = process.argv.includes("--reset");
const passwordHashPrefix = "scrypt";

function isHashedPassword(value) {
  return typeof value === "string" && value.startsWith(`${passwordHashPrefix}$`);
}

function hashPassword(password, saltKey) {
  const salt = createHash("sha256").update(String(saltKey)).digest("hex").slice(0, 32);
  const hash = scryptSync(password, salt, 64).toString("hex");
  return `${passwordHashPrefix}$${salt}$${hash}`;
}

function withHashedPasswords(state) {
  return {
    ...state,
    users: state.users.map((user) => ({
      ...user,
      password: isHashedPassword(user.password) ? user.password : hashPassword(user.password, user.id || user.email),
    })),
  };
}

async function fileExists(path) {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

async function sqliteStateStore() {
  const store = new SqliteDocumentStore({ dbPath: sqliteDbPath, sqlitePath: sqliteBinPath });
  await store.initialize();
  return store;
}

async function readActiveStateFromSqlite() {
  if (storageDriver !== "sqlite" || !(await fileExists(sqliteDbPath))) {
    return undefined;
  }
  const store = await sqliteStateStore();
  return store.read("state", undefined);
}

async function writeActiveStateToSqlite(state) {
  if (storageDriver !== "sqlite") {
    return;
  }
  const store = await sqliteStateStore();
  await store.write("state", state);
  await store.ensure("sessions", () => ({ sessions: [] }));
  await store.ensure("paymentOrders", () => ({ orders: [] }));
  await store.ensure("accessOutbox", () => ({ messages: [] }));
}

await mkdir(dataDir, { recursive: true });
await mkdir(stateBackupDir, { recursive: true });
await mkdir(coverUploadDir, { recursive: true });
await mkdir(materialUploadDir, { recursive: true });

const vite = await createServer({
  root: rootDir,
  appType: "custom",
  logLevel: "error",
  server: {
    middlewareMode: true,
  },
});

try {
  const { defaultState } = await vite.ssrLoadModule("/src/domain/seed.ts");
  const persistentState = withHashedPasswords(defaultState);
  await writeFile(seedPath, `${JSON.stringify(persistentState, null, 2)}\n`);

  let stateMissing = false;
  try {
    await stat(statePath);
  } catch {
    stateMissing = true;
  }

  if (shouldReset) {
    const previousState = (await readActiveStateFromSqlite()) || (stateMissing ? undefined : await readJsonFile(statePath));
    if (!stateMissing) {
      await backupStateFile(statePath, stateBackupDir, "before-seed-reset");
    }
    const nextState = await withPreservedLocalUploadReferences(persistentState, previousState, {
      coverUploadDir,
      materialUploadDir,
    });
    await writeJsonFile(statePath, nextState);
    await writeActiveStateToSqlite(nextState);
  } else if (stateMissing) {
    const restoredBackup = await restoreLatestStateBackup(statePath, stateBackupDir);
    if (!restoredBackup) {
      await writeJsonFile(statePath, persistentState);
    }
  }

  console.log(`Seed exported: ${seedPath}`);
} finally {
  await vite.close();
}
