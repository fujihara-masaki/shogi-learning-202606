import { mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const repoRoot = resolve(frontendDir, "..");
const backendDir = resolve(repoRoot, "backend");
const dbPath = process.env.SHOGI_DB_PATH ?? resolve(frontendDir, ".e2e", "shogi-e2e.db");
const nextMoveDbPath = process.env.NEXT_MOVE_DB_PATH ?? resolve(frontendDir, ".e2e", "next-move-e2e.db");
const port = process.env.E2E_BACKEND_PORT ?? "8000";
const frontendPort = process.env.E2E_FRONTEND_PORT ?? "5173";
const python = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");

// backend の CORS 許可オリジンはデフォルトで 5173 固定のため、
// E2E_FRONTEND_PORT を変えた場合でもブラウザからの API 呼び出しが通るように揃える。
const corsOrigins =
  process.env.SHOGI_CORS_ORIGINS ??
  `http://localhost:${frontendPort},http://127.0.0.1:${frontendPort}`;

mkdirSync(dirname(dbPath), { recursive: true });
mkdirSync(dirname(nextMoveDbPath), { recursive: true });
if (!process.env.NEXT_MOVE_DB_PATH) {
  rmSync(nextMoveDbPath, { force: true });
  const fixture = resolve(backendDir, "tests", "fixtures", "yaneuraou_book_sample.db");
  const env = { ...process.env, NEXT_MOVE_DB_PATH: nextMoveDbPath };
  for (const args of [
    ["-m", "app.importers.yaneuraou_book", fixture, "--name", "E2E YaneuraOu fixture", "--source-url", "https://example.test/book", "--license-name", "MIT License", "--limit", "2"],
    ["-m", "app.scripts.extract_learning_samples", "--source-id", "1", "--limit", "2", "--per-opening-limit", "2", "--seed", "1"],
  ]) {
    const result = spawnSync(python, args, { cwd: backendDir, env, stdio: "inherit" });
    if (result.status !== 0) process.exit(result.status ?? 1);
  }
}

const child = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
  {
    cwd: backendDir,
    env: { ...process.env, SHOGI_DB_PATH: dbPath, NEXT_MOVE_DB_PATH: nextMoveDbPath, E2E_BACKEND_PORT: port, SHOGI_CORS_ORIGINS: corsOrigins },
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
