import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "../api/client";

// One row of GET /metrics/cost-by-model, ordered most expensive first.
export interface CostByModelRow {
  model: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

// No bucket param: this endpoint groups by model over the whole window rather
// than over time.
export function useCostByModel() {
  return useQuery<CostByModelRow[]>({
    queryKey: ["cost-by-model"],
    queryFn: () => fetchJson<CostByModelRow[]>("/metrics/cost-by-model"),
  });
}
