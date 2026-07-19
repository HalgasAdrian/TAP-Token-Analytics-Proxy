import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useVolume } from "../hooks/useVolume";

// Shared card shell so the live chart and the A10 placeholders line up.
function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 font-medium text-gray-900">{title}</div>
      {children}
    </div>
  );
}

// IMPLEMENTED REFERENCE for the A10 chart components.
// Consumes the useVolume hook and renders request volume over time with
// Recharts. Note the explicit loading / error / empty states — the A10 charts
// should mirror this structure once their A9 hooks return data.
export function VolumeChart() {
  const { data, isLoading, isError, error } = useVolume();

  if (isLoading) {
    return (
      <ChartCard title="Request Volume">
        <div className="flex h-64 items-center justify-center text-sm text-gray-500">
          Loading…
        </div>
      </ChartCard>
    );
  }

  if (isError) {
    return (
      <ChartCard title="Request Volume">
        <div className="flex h-64 items-center justify-center text-sm text-red-600">
          Failed to load: {error instanceof Error ? error.message : "Unknown error"}
        </div>
      </ChartCard>
    );
  }

  const points = data ?? [];

  if (points.length === 0) {
    return (
      <ChartCard title="Request Volume">
        <div className="flex h-64 items-center justify-center text-sm text-gray-500">
          No request data yet.
        </div>
      </ChartCard>
    );
  }

  return (
    <ChartCard title="Request Volume">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={points} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="bucket" tick={{ fontSize: 12 }} stroke="#6b7280" />
            <YAxis allowDecimals={false} tick={{ fontSize: 12 }} stroke="#6b7280" />
            <Tooltip />
            <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
