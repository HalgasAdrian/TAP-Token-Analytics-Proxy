// Chart tokens, referenced by role rather than raw hex so every chart stays
// consistent and the palette can change in one place.
//
// These values are validated, not chosen by eye. Against this dashboard's white
// card surface the sets that actually share a chart pass every gate — lightness
// band, chroma floor, CVD separation, normal-vision floor, and 3:1 contrast:
//
//   latency p50 + p95 (blue + orange)   worst adjacent CVD dE 24.7, normal 33.6
//   blue vs red (never co-plotted)      worst all-pairs CVD dE 21.6, normal 32.3
//
// Re-validate before changing a hue. Note that orange and red fail against each
// other (normal dE 7.1) — they are deliberately never placed in the same chart.

export const VIZ = {
  // Categorical slots. Only latency plots two series at once.
  series1: "#2a78d6", // blue   — volume, cost, cache rate
  series2: "#eb6834", // orange — p95, paired with blue p50
  seriesError: "#e34948", // red — error rate, plotted alone

  // Chrome and ink. Text always wears an ink token, never a series color.
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  muted: "#898781",
  inkPrimary: "#0b0b0b",
  inkSecondary: "#52514e",
} as const;

/** Axis/label type size shared by every chart. */
export const AXIS_TICK = { fontSize: 12, fill: VIZ.muted } as const;

/**
 * Format a bucket timestamp for an axis tick.
 *
 * Minute and hour buckets only need a clock reading; coarser buckets need the
 * date. Showing the full ISO string would collide at any realistic width.
 */
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

/**
 * Format a USD amount that may be a fraction of a cent.
 *
 * Proxied calls routinely cost far less than $0.01, so a fixed 2-decimal
 * currency format would render every value as "$0.00".
 */
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
