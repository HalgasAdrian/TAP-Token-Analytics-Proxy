import { useQuery } from "@tanstack/react-query";
import { fetchJson, metricsPath, type Bucket } from "../api/client";

// Percentiles are null for a bucket with no measurable rows.
export interface LatencyPoint {
  bucket: string;
  p50: number | null;
  p95: number | null;
  count: number;
}

export function useLatency(bucket: Bucket = "hour") {
  return useQuery<LatencyPoint[]>({
    queryKey: ["latency", bucket],
    queryFn: () => fetchJson<LatencyPoint[]>(metricsPath("latency", bucket)),
  });
}
