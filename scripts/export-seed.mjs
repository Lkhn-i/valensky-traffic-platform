import { copyFile, mkdir, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { createHash, scryptSync } from "node:crypto";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const rootDir = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const dataDir = join(rootDir, "server", "data");
const seedPath = join(dataDir, "seed-state.json");
const statePath = join(dataDir, "app-state.json");
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

await mkdir(dataDir, { recursive: true });

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

  if (shouldReset || stateMissing) {
    await copyFile(seedPath, statePath);
  }

  console.log(`Seed exported: ${seedPath}`);
} finally {
  await vite.close();
}
