/** Shared native API origin and FastAPI error envelope handling. */
const API_BASE = (process.env.EXPO_PUBLIC_VERITAS_API_URL || "http://127.0.0.1:8765").replace(/\/$/, "");

export async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json() as { detail?: unknown };
      if (typeof payload.detail === "string" && payload.detail) message = payload.detail;
      else if (payload.detail != null) message = JSON.stringify(payload.detail);
    } catch {
      // A non-JSON error is still reported with its HTTP status.
    }
    throw new Error(message);
  }
  return response;
}
