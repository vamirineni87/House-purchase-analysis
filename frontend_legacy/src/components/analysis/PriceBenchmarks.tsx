"use client";

/**
 * Price Benchmarks component — compares asking price against
 * Zestimate, assessment, and assessment+7%.
 * Green if below, red if above.
 */

interface PriceBenchmarksProps {
  askPrice?: number;
  zestimate?: number;
  assessedValue?: number;
  compEstimate?: number;
}

function formatCurrency(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

function formatPct(n: number): string {
  const sign = n > 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(1)}%`;
}

function diffColor(diff: number): string {
  if (diff < -0.02) return "text-green-600";
  if (diff > 0.02) return "text-red-600";
  return "text-gray-600";
}

function diffBg(diff: number): string {
  if (diff < -0.02) return "bg-green-50 border-green-200";
  if (diff > 0.02) return "bg-red-50 border-red-200";
  return "bg-gray-50 border-gray-200";
}

interface BenchmarkRowProps {
  label: string;
  benchmark?: number;
  askPrice: number;
}

function BenchmarkRow({ label, benchmark, askPrice }: BenchmarkRowProps) {
  if (!benchmark) {
    return (
      <div className="border border-gray-200 rounded-lg p-3 bg-gray-50">
        <div className="text-xs text-gray-500 mb-1">{label}</div>
        <div className="text-sm text-gray-400">No data</div>
      </div>
    );
  }

  const diff = (askPrice - benchmark) / benchmark;

  return (
    <div className={`border rounded-lg p-3 ${diffBg(diff)}`}>
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-lg font-bold text-gray-900">
        {formatCurrency(benchmark)}
      </div>
      <div className="flex items-center gap-2 mt-1">
        <span className={`text-sm font-medium ${diffColor(diff)}`}>
          {formatPct(diff)}
        </span>
        <span className="text-xs text-gray-500">
          {diff > 0.02
            ? "Ask is above"
            : diff < -0.02
              ? "Ask is below"
              : "Near parity"}
        </span>
      </div>
    </div>
  );
}

export default function PriceBenchmarks({
  askPrice,
  zestimate,
  assessedValue,
  compEstimate,
}: PriceBenchmarksProps) {
  if (!askPrice) {
    return (
      <div className="text-sm text-gray-500">
        No list price available for benchmarks.
      </div>
    );
  }

  const assessedPlus7 = assessedValue
    ? Math.round(assessedValue * 1.07)
    : undefined;

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        Price Benchmarks vs Ask ({formatCurrency(askPrice)})
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <BenchmarkRow
          label="Zestimate"
          benchmark={zestimate}
          askPrice={askPrice}
        />
        <BenchmarkRow
          label="Assessed Value"
          benchmark={assessedValue}
          askPrice={askPrice}
        />
        <BenchmarkRow
          label="Assessed + 7%"
          benchmark={assessedPlus7}
          askPrice={askPrice}
        />
        <BenchmarkRow
          label="Comp Estimate"
          benchmark={compEstimate}
          askPrice={askPrice}
        />
      </div>
    </div>
  );
}
