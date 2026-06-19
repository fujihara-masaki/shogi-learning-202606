import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const repoRoot = resolve(frontendDir, "..");
const backendDir = resolve(repoRoot, "backend");
const dbPath = process.env.SHOGI_DB_PATH ?? resolve(frontendDir, ".e2e", "shogi-e2e.db");
const port = process.env.E2E_BACKEND_PORT ?? "8000";
const python = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");

mkdirSync(dirname(dbPath), { recursive: true });

const child = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
  {
    cwd: backendDir,
    env: { ...process.env, SHOGI_DB_PATH: dbPath, E2E_BACKEND_PORT: port },
    stdio: "inherit",
  },
);

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 0);
});
