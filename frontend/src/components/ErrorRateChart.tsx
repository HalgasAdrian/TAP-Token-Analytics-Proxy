import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Bucket } from "../api/client";
import { useErrors, type ErrorBucket } from "../hooks/useErrors";
import { AXIS_TICK, VIZ, formatBucket, formatPercent } from "../viz/tokens";
import { MetricCard, PlotArea } from "./MetricCard";

// Columns, not a line: errors are sparse spikes, and a line through mostly-zero
// buckets implies a continuity that is not there.
export function ErrorRateChart({ bucket }: { bucket: Bucket }) {
  const query = useErrors(bucket);

  return (
    <MetricCard
      title="Error Rate"
      subtitle="Non-2xx responses among forwarded requests"
      query={query}
      isEmpty={(summary) => summary.total === 0}
      headline={(summary) => formatPercent(summary.error_rate)}
    >
      {(summary) => (
        <PlotArea>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={summary.series}
              margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke={VIZ.grid}
                vertical={false}
              />
              <XAxis
                dataKey="bucket"
                tickFormatter={(value) => formatBucket(value, bucket)}
                tick={AXIS_TICK}
                stroke={VIZ.axis}
              />
              <YAxis
                domain={[0, 1]}
                tickFormatter={formatPercent}
                tick={AXIS_TICK}
                stroke={VIZ.axis}
              />
              <Tooltip
                labelFormatter={(value) => formatBucket(String(value), bucket)}
                formatter={(value: number, _name, item) => {
                  const row = item?.payload as ErrorBucket | undefined;
                  const detail = row
                    ? ` (${row.errors} of ${row.total})`
                    : "";
                  return [`${formatPercent(value)}${detail}`, "error rate"];
                }}
              />
              <Bar
                dataKey="error_rate"
                fill={VIZ.seriesError}
                radius={[4, 4, 0, 0]}
                maxBarSize={48}
              />
            </BarChart>
          </ResponsiveContainer>
        </PlotArea>
      )}
    </MetricCard>
  );
}
