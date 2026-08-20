import { useQuery } from "@tanstack/react-query";
import { fetchJson, metricsPath, type Bucket } from "../api/client";

// One time-bucketed request-volume point returned by GET /metrics/volume.
export interface VolumePoint {
  bucket: string;
  count: number;
}

// The shape every metrics hook here follows: a queryKey that includes each
// input affecting the result (so changing granularity refetches rather than
// serving a stale cache entry) plus a queryFn hitting one /metrics endpoint.
export function useVolume(bucket: Bucket = "hour") {
  return useQuery<VolumePoint[]>({
    queryKey: ["volume", bucket],
    queryFn: () => fetchJson<VolumePoint[]>(metricsPath("volume", bucket)),
  });
}
