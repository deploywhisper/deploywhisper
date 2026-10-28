import type { paths } from "./schema";

export interface ApiEnvelope<TData, TMeta = unknown> {
  data: TData;
  meta: TMeta;
}

type JsonResponse<
  TPath extends keyof paths,
  TMethod extends keyof paths[TPath],
> = paths[TPath][TMethod] extends {
  responses: {
    200: {
      content: {
        "application/json": infer TResponse;
      };
    };
  };
}
  ? TResponse
  : never;

type EnvelopeFrom<TResponse> = TResponse extends {
  data: infer TData;
  meta: infer TMeta;
}
  ? ApiEnvelope<TData, TMeta>
  : never;

export type HealthEnvelope = EnvelopeFrom<JsonResponse<"/api/v1/health", "get">>;

export class ApiClientError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly retryable?: boolean;
  readonly correlationId?: string;

  constructor(message: string, status: number, metadata: { code?: string; retryable?: boolean; correlationId?: string } = {}) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = metadata.code;
    this.retryable = metadata.retryable;
    this.correlationId = metadata.correlationId;
  }
}

const safeErrorCodes = new Set([
  "authentication_required", "permission_denied", "binding_conflict",
  "request_validation_failed", "quota_exceeded", "authority_unavailable",
]);

function errorMetadata(body: unknown) {
  const error = typeof body === "object" && body !== null && "error" in body ? body.error : null;
  if (typeof error !== "object" || error === null) return {};
  const code = "code" in error && typeof error.code === "string" && safeErrorCodes.has(error.code) ? error.code : undefined;
  const details = "details" in error ? error.details : null;
  if (!code || typeof details !== "object" || details === null) return { code };
  return {
    code,
    retryable: "retryable" in details && typeof details.retryable === "boolean" ? details.retryable : undefined,
    correlationId: "correlation_id" in details && typeof details.correlation_id === "string" && /^[a-f0-9]{32}$/.test(details.correlation_id) ? details.correlation_id : undefined,
  };
}

function isEnvelope(value: unknown): value is ApiEnvelope<unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    "data" in value &&
    "meta" in value
  );
}

export async function requestEnvelope<TEnvelope extends ApiEnvelope<unknown>>(
  path: string,
  init: RequestInit = {},
): Promise<TEnvelope> {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  const response = await fetch(path, { ...init, headers });
  // Parse failures must never expose a server body through a SyntaxError.
  const body: unknown = await response.json().catch(() => undefined);

  if (!response.ok) {
    const pathname = path.split("?")[0];
    // Public report password challenges do not describe the human session.
    const handledChallenge = ["/api/v1/auth/login", "/api/v1/auth/session"].includes(pathname)
      || /^\/api\/v1\/analyses\/[^/]+\/shared(?:\/unlock)?$/.test(pathname);
    if (response.status === 401 && !handledChallenge && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("dw:identity-expired"));
    }
    // Preserve this existing UI label using a fixed route, never caller data.
    const message = pathname === "/api/v1/settings/provider"
      ? "Request failed: /api/v1/settings/provider"
      : "Request failed.";
    throw new ApiClientError(message, response.status, errorMetadata(body));
  }

  if (!isEnvelope(body)) {
    throw new ApiClientError("Unexpected API response.", response.status);
  }

  return body as TEnvelope;
}

export async function requestData<TData>(
  path: string,
  init: RequestInit = {},
): Promise<TData> {
  const envelope = await requestEnvelope<ApiEnvelope<TData>>(path, init);
  return envelope.data;
}

export function getHealth(): Promise<HealthEnvelope> {
  return requestEnvelope<HealthEnvelope>("/api/v1/health");
}
