import type { ReactElement } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Bucket } from "../api/client";
import { useLatency } from "../hooks/useLatency";
import { AXIS_TICK, VIZ, formatBucket, formatMs } from "../viz/tokens";
import { MetricCard, PlotArea } from "./MetricCard";

// The only chart with two series, and so the only one using categorical color.
// Both share one millisecond axis.

/** Labels the final point of a line, so identity is not carried by color alone. */
function endLabel(text: string, lastIndex: number) {
  // Recharts types a label renderer as always returning an element, hence the
  // empty group rather than null.
  return function EndLabel(props: {
    x?: number;
    y?: number;
    index?: number;
    value?: number | null;
  }): ReactElement {
    const { x, y, index, value } = props;
    if (index !== lastIndex || value == null || x == null || y == null) {
      return <g />;
    }
    return (
      <text
        x={x}
        y={y}
        dx={8}
        dy={4}
        fill={VIZ.inkSecondary}
        fontSize={11}
        fontWeight={600}
      >
        {text}
      </text>
    );
  };
}

export function LatencyChart({ bucket }: { bucket: Bucket }) {
  const query = useLatency(bucket);

  return (
    <MetricCard
      title="Latency"
      subtitle={`Median and 95th percentile per ${bucket}`}
      query={query}
      isEmpty={(points) => points.length === 0}
    >
      {(points) => {
        const lastIndex = points.length - 1;
        return (
          <PlotArea>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={points}
                margin={{ top: 8, right: 48, bottom: 8, left: 0 }}
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
                  tick={AXIS_TICK}
                  stroke={VIZ.axis}
                  tickFormatter={(value: number) => `${Math.round(value)}`}
                  label={{
                    value: "ms",
                    angle: -90,
                    position: "insideLeft",
                    style: { fill: VIZ.muted, fontSize: 11 },
                  }}
                />
                <Tooltip
                  labelFormatter={(value) =>
                    formatBucket(String(value), bucket)
                  }
                  formatter={(value: number, name) => [
                    formatMs(value),
                    name === "p50" ? "median" : "p95",
                  ]}
                />
                <Legend
                  verticalAlign="top"
                  align="right"
                  height={28}
                  iconType="plainline"
                  formatter={(value) => (
                    <span style={{ color: VIZ.inkSecondary, fontSize: 12 }}>
                      {value === "p50" ? "median" : "p95"}
                    </span>
                  )}
                />
                <Line
                  type="monotone"
                  dataKey="p50"
                  stroke={VIZ.series1}
                  strokeWidth={2}
                  dot={{ r: 4, strokeWidth: 0, fill: VIZ.series1 }}
                  activeDot={{ r: 5 }}
                  connectNulls
                  label={endLabel("median", lastIndex)}
                />
                <Line
                  type="monotone"
                  dataKey="p95"
                  stroke={VIZ.series2}
                  strokeWidth={2}
                  dot={{ r: 4, strokeWidth: 0, fill: VIZ.series2 }}
                  activeDot={{ r: 5 }}
                  connectNulls
                  label={endLabel("p95", lastIndex)}
                />
              </LineChart>
            </ResponsiveContainer>
          </PlotArea>
        );
      }}
    </MetricCard>
  );
}
