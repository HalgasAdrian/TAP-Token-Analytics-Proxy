import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useCostByModel, type CostByModelRow } from "../hooks/useCostByModel";
import { AXIS_TICK, VIZ, formatUsd } from "../viz/tokens";
import { MetricCard, PlotArea } from "./MetricCard";

// Spend per model: comparing magnitude across named categories, so a bar chart
// in one hue — the model name is on the axis, and coloring each bar separately
// would imply a distinction that is not in the data.
//
// Horizontal, because model ids are long enough to collide as vertical ticks.
export function CostByModelChart() {
  const query = useCostByModel();

  const total = (rows: CostByModelRow[]) =>
    rows.reduce((sum, row) => sum + row.cost_usd, 0);

  return (
    <MetricCard
      title="Cost by Model"
      subtitle="Total spend per model, most expensive first"
      query={query}
      isEmpty={(rows) => rows.length === 0}
      headline={(rows) => formatUsd(total(rows))}
    >
      {(rows) => (
        <PlotArea>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={rows}
              layout="vertical"
              margin={{ top: 8, right: 24, bottom: 8, left: 8 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke={VIZ.grid}
                horizontal={false}
              />
              <XAxis
                type="number"
                tickFormatter={formatUsd}
                tick={AXIS_TICK}
                stroke={VIZ.axis}
              />
              <YAxis
                type="category"
                dataKey="model"
                width={140}
                tick={AXIS_TICK}
                stroke={VIZ.axis}
              />
              <Tooltip
                formatter={(value: number, _name, item) => {
                  const row = item?.payload as CostByModelRow | undefined;
                  if (!row) return [formatUsd(value), "cost"];
                  return [
                    `${formatUsd(row.cost_usd)} · ${row.requests} req · ` +
                      `${row.input_tokens.toLocaleString()} in / ` +
                      `${row.output_tokens.toLocaleString()} out tokens`,
                    "cost",
                  ];
                }}
              />
              <Bar
                dataKey="cost_usd"
                fill={VIZ.series1}
                radius={[0, 4, 4, 0]}
                maxBarSize={28}
              />
            </BarChart>
          </ResponsiveContainer>
        </PlotArea>
      )}
    </MetricCard>
  );
}
