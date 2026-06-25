import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const backendPort = process.env.E2E_BACKEND_PORT ?? "8000";
const frontendPort = process.env.E2E_FRONTEND_PORT ?? "5173";
const host = "127.0.0.1";

const npmArgs = ["run", "dev", "--", "--host", host, "--port", frontendPort];
const spawnOptions = {
  cwd: frontendDir,
  env: {
    ...process.env,
    VITE_API_BASE: `http://${host}:${backendPort}`,
  },
  stdio: "inherit",
};

const child = process.platform === "win32"
  ? spawn("cmd.exe", ["/d", "/s", "/c", "npm.cmd", ...npmArgs], spawnOptions)
  : spawn("npm", npmArgs, spawnOptions);

child.on("error", (error) => {
  const command = process.platform === "win32"
    ? `cmd.exe /d /s /c npm.cmd ${npmArgs.join(" ")}`
    : `npm ${npmArgs.join(" ")}`;

  console.error("Failed to start the E2E frontend dev server.");
  console.error(`Command: ${command}`);
  console.error(`Working directory: ${frontendDir}`);
  console.error(`VITE_API_BASE: http://${host}:${backendPort}`);
  console.error(`Frontend URL: http://${host}:${frontendPort}`);
  console.error(error);
  process.exit(1);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 0);
});
