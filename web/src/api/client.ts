// Thin fetch wrapper. All server state goes through TanStack Query hooks in ./hooks.ts.
export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
  }
  get forbidden() { return this.status === 403; }
  get reason(): string | undefined {
    const d = this.detail as { reason?: string } | undefined;
    return d?.reason;
  }
}

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const body = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new ApiError(res.status, (body as { detail?: unknown })?.detail ?? body);
  return body as T;
}

export const post = <T>(path: string, data?: unknown) =>
  api<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });
