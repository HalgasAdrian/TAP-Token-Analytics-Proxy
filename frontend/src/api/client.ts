// Empty means same origin: in production the API serves this bundle, and in
// development Vite proxies /metrics to it. Either way there is no cross-origin
// request and no URL baked into the build.
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "";

export type Bucket = "minute" | "hour" | "day" | "week" | "month";

export const BUCKETS: readonly Bucket[] = [
  "minute",
  "hour",
  "day",
  "week",
  "month",
];

/** Throws on any non-2xx so TanStack Query surfaces an error state. */
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

export function metricsPath(name: string, bucket: Bucket): string {
  return `/metrics/${name}?bucket=${encodeURIComponent(bucket)}`;
}
