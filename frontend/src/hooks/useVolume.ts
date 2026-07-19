import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "../api/client";

// One time-bucketed request-volume point returned by GET /metrics/volume.
// The metrics aggregation (A7) fills these buckets; the hook only types them.
export interface VolumePoint {
  bucket: string;
  count: number;
}

// IMPLEMENTED REFERENCE for the A9 assignment hooks.
// A TanStack Query hook: a stable queryKey plus a queryFn that hits the API.
// The four A9 hooks (useCostByModel, useLatency, useCache, useErrors) mirror
// this shape but point at their own /metrics/<name> endpoint.
export function useVolume() {
  return useQuery<VolumePoint[]>({
    queryKey: ["volume"],
    queryFn: () => fetchJson<VolumePoint[]>("/metrics/volume"),
  });
}
