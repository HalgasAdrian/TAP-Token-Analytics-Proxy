import { useQuery } from "@tanstack/react-query";
import { fetchJson, metricsPath, type Bucket } from "../api/client";

export interface ErrorBucket {
  bucket: string;
  total: number;
  errors: number;
  error_rate: number;
}

// GET /metrics/errors mirrors the cache endpoint: window total plus series.
export interface ErrorSummary {
  total: number;
  errors: number;
  error_rate: number;
  series: ErrorBucket[];
}

export function useErrors(bucket: Bucket = "hour") {
  return useQuery<ErrorSummary>({
    queryKey: ["errors", bucket],
    queryFn: () => fetchJson<ErrorSummary>(metricsPath("errors", bucket)),
  });
}
