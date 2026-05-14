import { chmod, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { spawn } from "node:child_process";

const defaultMaxOutputBytes = 64 * 1024 * 1024;

function sqlString(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}

function sqlTextLiteral(value) {
  return `CAST(X'${Buffer.from(String(value), "utf8").toString("hex")}' AS TEXT)`;
}

function runSqlite(sqlitePath, dbPath, script, maxOutputBytes = defaultMaxOutputBytes) {
  return new Promise((resolve, reject) => {
    const child = spawn(sqlitePath, ["-batch", dbPath], {
      stdio: ["pipe", "pipe", "pipe"],
    });
    const stdout = [];
    const stderr = [];
    let stdoutSize = 0;
    let stderrSize = 0;

    child.stdout.on("data", (chunk) => {
      stdoutSize += chunk.length;
      if (stdoutSize <= maxOutputBytes) {
        stdout.push(chunk);
      }
    });
    child.stderr.on("data", (chunk) => {
      stderrSize += chunk.length;
      if (stderrSize <= maxOutputBytes) {
        stderr.push(chunk);
      }
    });
    child.on("error", reject);
    child.on("close", (code) => {
      const stderrText = Buffer.concat(stderr).toString("utf8").trim();
      if (code !== 0) {
        reject(new Error(stderrText || `sqlite3 exited with code ${code}`));
        return;
      }
      resolve(Buffer.concat(stdout).toString("utf8"));
    });
    child.stdin.end(script);
  });
}

export class SqliteDocumentStore {
  constructor({ dbPath, sqlitePath = "sqlite3" }) {
    this.dbPath = dbPath;
    this.sqlitePath = sqlitePath;
  }

  async initialize() {
    await mkdir(dirname(this.dbPath), { recursive: true });
    await runSqlite(
      this.sqlitePath,
      this.dbPath,
      [
        "PRAGMA journal_mode=WAL;",
        "PRAGMA busy_timeout=5000;",
        "CREATE TABLE IF NOT EXISTS app_documents (",
        "  key TEXT PRIMARY KEY,",
        "  value TEXT NOT NULL,",
        "  updated_at TEXT NOT NULL",
        ");",
      ].join("\n"),
    );
    await this.secureFiles();
  }

  async has(key) {
    const output = await runSqlite(
      this.sqlitePath,
      this.dbPath,
      `SELECT COUNT(*) FROM app_documents WHERE key = ${sqlString(key)};\n`,
    );
    return Number(output.trim()) > 0;
  }

  async ensure(key, valueFactory) {
    if (await this.has(key)) {
      return;
    }
    await this.write(key, await valueFactory());
  }

  async read(key, fallbackValue) {
    const output = await runSqlite(
      this.sqlitePath,
      this.dbPath,
      `SELECT hex(value) FROM app_documents WHERE key = ${sqlString(key)} LIMIT 1;\n`,
    );
    const hex = output.trim();
    if (!hex) {
      return fallbackValue;
    }
    return JSON.parse(Buffer.from(hex, "hex").toString("utf8"));
  }

  async write(key, value) {
    const serialized = JSON.stringify(value);
    const now = new Date().toISOString();
    await runSqlite(
      this.sqlitePath,
      this.dbPath,
      [
        "BEGIN IMMEDIATE;",
        "INSERT INTO app_documents (key, value, updated_at)",
        `VALUES (${sqlString(key)}, ${sqlTextLiteral(serialized)}, ${sqlString(now)})`,
        "ON CONFLICT(key) DO UPDATE SET",
        "  value = excluded.value,",
        "  updated_at = excluded.updated_at;",
        "COMMIT;",
      ].join("\n"),
      Math.max(defaultMaxOutputBytes, serialized.length * 2),
    );
    await this.secureFiles();
  }

  async secureFiles() {
    await Promise.all(
      [this.dbPath, `${this.dbPath}-wal`, `${this.dbPath}-shm`].map((path) => chmod(path, 0o600).catch(() => {})),
    );
  }
}
