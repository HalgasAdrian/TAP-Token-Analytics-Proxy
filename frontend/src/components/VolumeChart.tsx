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
import { useVolume } from "../hooks/useVolume";
import { AXIS_TICK, VIZ, formatBucket } from "../viz/tokens";
import { MetricCard, PlotArea } from "./MetricCard";

export function VolumeChart({ bucket }: { bucket: Bucket }) {
  const query = useVolume(bucket);

  return (
    <MetricCard
      title="Request Volume"
      subtitle={`Proxied requests per ${bucket}`}
      query={query}
      isEmpty={(points) => points.length === 0}
    >
      {(points) => (
        <PlotArea>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={points}
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
              <YAxis allowDecimals={false} tick={AXIS_TICK} stroke={VIZ.axis} />
              <Tooltip
                labelFormatter={(value) => formatBucket(String(value), bucket)}
                formatter={(value: number) => [value, "requests"]}
              />
              <Bar
                dataKey="count"
                fill={VIZ.series1}
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
