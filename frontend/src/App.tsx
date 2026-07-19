import { VolumeChart } from "./components/VolumeChart";
import { CostByModelChart } from "./components/CostByModelChart";
import { LatencyChart } from "./components/LatencyChart";
import { CacheChart } from "./components/CacheChart";
import { ErrorRateChart } from "./components/ErrorRateChart";

// Dashboard shell. VolumeChart is the live worked reference; the other four
// are A10 placeholder cards until their assignments are implemented.
export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-5">
          <h1 className="text-xl font-semibold">TAP — Token Analytics Proxy</h1>
          <p className="text-sm text-gray-500">
            Usage, cost, latency, cache, and error metrics for proxied traffic.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <VolumeChart />
          <CostByModelChart />
          <LatencyChart />
          <CacheChart />
          <ErrorRateChart />
        </div>
      </main>
    </div>
  );
}
