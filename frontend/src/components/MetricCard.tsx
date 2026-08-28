import type { ReactNode } from "react";

const PANEL_HEIGHT = "h-64";

function Panel({ children }: { children: ReactNode }) {
  return (
    <div className={`flex ${PANEL_HEIGHT} items-center justify-center text-sm`}>
      {children}
    </div>
  );
}

export interface QueryLike<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
}

interface MetricCardProps<T> {
  title: string;
  subtitle?: string;
  query: QueryLike<T>;
  isEmpty: (data: T) => boolean;
  headline?: (data: T) => ReactNode;
  children: (data: T) => ReactNode;
}

export function MetricCard<T>({
  title,
  subtitle,
  query,
  isEmpty,
  headline,
  children,
}: MetricCardProps<T>) {
  const { data, isLoading, isError, error } = query;

  let body: ReactNode;
  if (isLoading) {
    body = <Panel><span className="text-gray-500">Loading…</span></Panel>;
  } else if (isError) {
    body = (
      <Panel>
        <span className="px-4 text-center text-red-600">
          Failed to load:{" "}
          {error instanceof Error ? error.message : "Unknown error"}
        </span>
      </Panel>
    );
  } else if (data === undefined || isEmpty(data)) {
    body = (
      <Panel>
        <span className="text-gray-500">
          No data yet — send a request through the proxy.
        </span>
      </Panel>
    );
  } else {
    body = children(data);
  }

  const showHeadline =
    headline && !isLoading && !isError && data !== undefined && !isEmpty(data);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <div className="font-medium text-gray-900">{title}</div>
          {subtitle && (
            <div className="mt-0.5 text-xs text-gray-500">{subtitle}</div>
          )}
        </div>
        {showHeadline && (
          <div className="text-2xl leading-none text-gray-900">
            {headline(data)}
          </div>
        )}
      </div>
      {body}
    </div>
  );
}

/** Fixed height so every plot area lines up across cards. */
export function PlotArea({ children }: { children: ReactNode }) {
  return <div className={PANEL_HEIGHT}>{children}</div>;
}
