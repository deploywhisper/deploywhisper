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

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
  }
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
  const response = await fetch(path, {
    headers: {
      Accept: "application/json",
      ...init.headers,
    },
    ...init,
  });

  const body: unknown = await response.json();

  if (!response.ok) {
    throw new ApiClientError(`Request failed: ${path}`, response.status);
  }

  if (!isEnvelope(body)) {
    throw new ApiClientError(`Unexpected API envelope: ${path}`, response.status);
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
