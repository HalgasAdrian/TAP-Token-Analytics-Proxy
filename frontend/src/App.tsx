import { useState } from "react";
import { BUCKETS, type Bucket } from "./api/client";
import { VolumeChart } from "./components/VolumeChart";
import { CostByModelChart } from "./components/CostByModelChart";
import { LatencyChart } from "./components/LatencyChart";
import { CacheChart } from "./components/CacheChart";
import { ErrorRateChart } from "./components/ErrorRateChart";

// Granularity lives here so the whole board reads at one scale, rather than
// each card carrying its own control.
export default function App() {
  const [bucket, setBucket] = useState<Bucket>("hour");

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-end justify-between gap-4 px-4 py-5">
          <div>
            <h1 className="text-xl font-semibold">TAP — Token Analytics Proxy</h1>
            <p className="text-sm text-gray-500">
              Usage, cost, latency, cache, and error metrics for proxied traffic.
            </p>
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-600">
            Granularity
            <select
              value={bucket}
              onChange={(event) => setBucket(event.target.value as Bucket)}
              className="rounded-md border border-gray-300 bg-white px-2 py-1 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {BUCKETS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <VolumeChart bucket={bucket} />
          <CostByModelChart />
          <LatencyChart bucket={bucket} />
          <CacheChart bucket={bucket} />
          <ErrorRateChart bucket={bucket} />
        </div>
      </main>
    </div>
  );
}
