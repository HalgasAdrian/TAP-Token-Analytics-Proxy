// Small typed API client for the TAP dashboard.
//
// API_BASE is read from the Vite env (VITE_API_BASE); it falls back to the
// local backend default. fetchJson is a thin wrapper around fetch that throws
// on any non-2xx response so TanStack Query can surface an error state.
//
// SECURITY: this client never sends or stores Authorization headers or API
// keys. The dashboard only reads aggregated, non-sensitive /metrics data.

export const API_BASE: string =
  import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function fetchJson<T = unknown>(path: string): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(
      `Request to ${path} failed: ${response.status} ${response.statusText}`,
    );
  }

  return (await response.json()) as T;
}
