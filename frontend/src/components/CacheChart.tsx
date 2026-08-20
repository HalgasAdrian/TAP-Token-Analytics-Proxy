import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Bucket } from "../api/client";
import { useCache, type CacheBucket } from "../hooks/useCache";
import { AXIS_TICK, VIZ, formatBucket, formatPercent } from "../viz/tokens";
import { MetricCard, PlotArea } from "./MetricCard";

// Cache hit rate: one headline ratio plus its trend. The window total is the
// number worth reading, so it leads as a stat figure; the area beneath shows
// whether it is improving. Single series — no legend needed.
export function CacheChart({ bucket }: { bucket: Bucket }) {
  const query = useCache(bucket);

  return (
    <MetricCard
      title="Cache Hit Rate"
      subtitle="Share of requests served from Redis instead of the provider"
      query={query}
      isEmpty={(summary) => summary.total === 0}
      headline={(summary) => formatPercent(summary.hit_rate)}
    >
      {(summary) => (
        <PlotArea>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={summary.series}
              margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
            >
              <defs>
                <linearGradient id="cacheFill" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor={VIZ.series1}
                    stopOpacity={0.28}
                  />
                  <stop
                    offset="100%"
                    stopColor={VIZ.series1}
                    stopOpacity={0.02}
                  />
                </linearGradient>
              </defs>
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
              {/* Fixed 0–1 domain: a rate chart that autoscales makes a 2%
                  hit rate look like a full one. */}
              <YAxis
                domain={[0, 1]}
                tickFormatter={formatPercent}
                tick={AXIS_TICK}
                stroke={VIZ.axis}
              />
              <Tooltip
                labelFormatter={(value) => formatBucket(String(value), bucket)}
                formatter={(value: number, _name, item) => {
                  const row = item?.payload as CacheBucket | undefined;
                  const detail = row
                    ? ` (${row.hits} hit / ${row.misses} miss)`
                    : "";
                  return [`${formatPercent(value)}${detail}`, "hit rate"];
                }}
              />
              <Area
                type="monotone"
                dataKey="hit_rate"
                stroke={VIZ.series1}
                strokeWidth={2}
                fill="url(#cacheFill)"
                dot={{ r: 4, strokeWidth: 0, fill: VIZ.series1 }}
                activeDot={{ r: 5 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </PlotArea>
      )}
    </MetricCard>
  );
}
