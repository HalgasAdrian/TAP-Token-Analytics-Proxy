// Validated against the white card surface for lightness band, chroma, CVD
// separation, and contrast. Blue + orange (the only pair sharing a chart) clear
// every gate; orange and red do not, and are never co-plotted.

export const VIZ = {
  series1: "#2a78d6",
  series2: "#eb6834",
  seriesError: "#e34948",

  grid: "#e1e0d9",
  axis: "#c3c2b7",
  muted: "#898781",
  inkPrimary: "#0b0b0b",
  inkSecondary: "#52514e",
} as const;

export const AXIS_TICK = { fontSize: 12, fill: VIZ.muted } as const;

/** Minute and hour buckets need a clock reading; coarser ones need the date. */
export function formatBucket(iso: string | null, bucket: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;

  if (bucket === "minute" || bucket === "hour") {
    return date.toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Proxied calls often cost a fraction of a cent, which 2dp would render as $0.00. */
export function formatUsd(value: number): string {
  if (value === 0) return "$0";
  if (Math.abs(value) < 0.01) return `$${value.toFixed(6)}`;
  return `$${value.toFixed(2)}`;
}

export function formatPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(1)}%`;
}

export function formatMs(value: number | null): string {
  if (value === null) return "—";
  return `${Math.round(value)} ms`;
}
