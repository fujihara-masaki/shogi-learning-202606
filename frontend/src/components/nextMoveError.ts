import { ApiError } from "../api/client";

export function errorMessage(error: unknown, prefix: string): string {
  const detail = error instanceof ApiError ? error.detail : error instanceof Error ? error.message : String(error);
  return `${prefix}: ${detail}`;
}
