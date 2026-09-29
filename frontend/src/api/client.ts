import type { ApiErrorBody } from "../types/api";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string | undefined;
  readonly details: unknown;

  constructor(message: string, status: number, code = "NETWORK_ERROR", requestId?: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.details = details;
  }
}

export function normalizeApiOrigin(value: string): string {
  const url = new URL(value.trim());
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error("API URL must use http or https.");
  if (url.username || url.password) throw new Error("API URL must not contain credentials.");
  return url.toString().replace(/\/$/, "");
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.code === "string" && typeof record.message === "string";
}

export class ApiClient {
  readonly origin: string;

  constructor(origin: string) {
    this.origin = normalizeApiOrigin(origin);
  }

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response: Response;
    try {
      const headers = new Headers(init.headers);
      if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
      response = await fetch(`${this.origin}${path}`, { ...init, headers });
    } catch (error) {
      throw new ApiError(error instanceof Error ? error.message : "Application API is unreachable.", 0);
    }
    const requestId = response.headers.get("X-Request-ID") ?? undefined;
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    let body: unknown;
    try { body = text ? JSON.parse(text) : undefined; }
    catch { throw new ApiError("Server returned invalid JSON.", response.status, "INVALID_RESPONSE", requestId); }
    if (!response.ok) {
      if (isApiErrorBody(body)) throw new ApiError(body.message, response.status, body.code, body.request_id || requestId, body.details);
      throw new ApiError(`Request failed with HTTP ${response.status}.`, response.status, "HTTP_ERROR", requestId);
    }
    return body as T;
  }

  get<T>(path: string, signal?: AbortSignal) { return this.request<T>(path, signal ? { signal } : {}); }
  post<T>(path: string, body?: unknown, signal?: AbortSignal) {
    const init: RequestInit = { method: "POST" };
    if (body !== undefined) init.body = JSON.stringify(body);
    if (signal) init.signal = signal;
    return this.request<T>(path, init);
  }
  upload<T>(path: string, file: File, signal?: AbortSignal) {
    const form = new FormData(); form.append("file", file);
    const init: RequestInit = { method: "POST", body: form };
    if (signal) init.signal = signal;
    return this.request<T>(path, init);
  }
}
