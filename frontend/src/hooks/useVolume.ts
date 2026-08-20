import { useQuery } from "@tanstack/react-query";
import { fetchJson, metricsPath, type Bucket } from "../api/client";

export interface VolumePoint {
  bucket: string;
  count: number;
}

// The bucket belongs in the queryKey so changing granularity refetches rather
// than serving a stale entry. Every hook here follows that shape.
export function useVolume(bucket: Bucket = "hour") {
  return useQuery<VolumePoint[]>({
    queryKey: ["volume", bucket],
    queryFn: () => fetchJson<VolumePoint[]>(metricsPath("volume", bucket)),
  });
}
