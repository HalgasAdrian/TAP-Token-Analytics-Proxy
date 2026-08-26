import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "../api/client";

export interface CostByModelRow {
  model: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  // Input tokens the provider served from its prompt cache, and what that
  // discount avoided. Distinct from TAP's own cache, which skips the call.
  cached_input_tokens: number;
  cache_savings_usd: number;
  cost_usd: number;
}

// No bucket param: this endpoint groups by model, not over time.
export function useCostByModel() {
  return useQuery<CostByModelRow[]>({
    queryKey: ["cost-by-model"],
    queryFn: () => fetchJson<CostByModelRow[]>("/metrics/cost-by-model"),
  });
}
