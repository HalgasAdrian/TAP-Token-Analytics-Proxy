import { useQuery } from "@tanstack/react-query";
import { fetchJson, metricsPath, type Bucket } from "../api/client";

export interface CacheBucket {
  bucket: string;
  total: number;
  hits: number;
  misses: number;
  hit_rate: number;
}

// GET /metrics/cache returns the window total alongside its per-bucket series,
// so the headline figure and the trend always agree.
export interface CacheSummary {
  total: number;
  hits: number;
  misses: number;
  hit_rate: number;
  series: CacheBucket[];
}

export function useCache(bucket: Bucket = "hour") {
  return useQuery<CacheSummary>({
    queryKey: ["cache", bucket],
    queryFn: () => fetchJson<CacheSummary>(metricsPath("cache", bucket)),
  });
}
