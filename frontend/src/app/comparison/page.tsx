"use client";

/**
 * Property comparison page.
 * Select 2-5 properties and view side-by-side weighted scoring.
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Badge from "@/components/common/Badge";
import type {
  PropertySummary,
  ComparisonResult,
} from "@/types/property";

const CATEGORIES = [
  "financial",
  "condition",
  "location",
  "risk",
  "hoa",
  "surrounding",
];

function formatScore(n: number): string {
  return n.toFixed(1);
}

export default function ComparisonPage() {
  const [properties, setProperties] = useState<PropertySummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [propertiesLoading, setPropertiesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProperties()
      .then(setProperties)
      .catch(() => {})
      .finally(() => setPropertiesLoading(false));
  }, []);

  function toggleProperty(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 5) {
        next.add(id);
      }
      return next;
    });
    setResult(null);
  }

  async function runComparison() {
    if (selected.size < 2) {
      setError("Select at least 2 properties to compare.");
      return;
    }

    setError(null);
    setLoading(true);
    try {
      const data = await api.compareProperties({
        property_ids: Array.from(selected),
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Compare Properties</h1>

      {/* Property selector */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">
          Select 2-5 properties ({selected.size} selected)
        </h2>

        {propertiesLoading ? (
          <div className="text-sm text-gray-500">Loading properties...</div>
        ) : properties.length === 0 ? (
          <div className="text-sm text-gray-500">
            No properties available. Add some first.
          </div>
        ) : (
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {properties.map((p) => (
              <label
                key={p.id}
                className={`flex items-center gap-3 p-2 rounded cursor-pointer hover:bg-gray-50 ${
                  selected.has(p.id) ? "bg-blue-50" : ""
                }`}
              >
                <input
                  type="checkbox"
                  checked={selected.has(p.id)}
                  onChange={() => toggleProperty(p.id)}
                  disabled={!selected.has(p.id) && selected.size >= 5}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-900 flex-1">
                  {p.address || "No address"}
                </span>
                {p.county && (
                  <Badge
                    label={p.county}
                    variant={p.county === "fairfax" ? "info" : "warning"}
                  />
                )}
              </label>
            ))}
          </div>
        )}

        <div className="mt-4">
          <button
            onClick={runComparison}
            disabled={selected.size < 2 || loading}
            className="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Comparing..." : "Compare Selected"}
          </button>
        </div>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 rounded px-3 py-2 mb-4">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6">
          {/* Ranking */}
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">
              Overall Ranking
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3">
              {result.properties.map((ps) => (
                <div
                  key={ps.property_id}
                  className={`bg-white border rounded-lg p-4 text-center ${
                    ps.rank === 1
                      ? "border-blue-300 ring-2 ring-blue-100"
                      : "border-gray-200"
                  }`}
                >
                  <div className="text-2xl font-bold text-gray-300 mb-1">
                    #{ps.rank}
                  </div>
                  <div className="text-sm font-medium text-gray-900 mb-1 truncate">
                    {ps.address || ps.property_id.slice(0, 8)}
                  </div>
                  <div className="text-xl font-bold text-blue-600">
                    {formatScore(ps.total_score)}
                  </div>
                  <div className="text-xs text-gray-500">out of 100</div>
                </div>
              ))}
            </div>
          </div>

          {/* Side-by-side metrics grid */}
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">
              Category Scores
            </h2>
            <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 text-gray-600 text-left">
                    <th className="px-3 py-2 font-medium">Category</th>
                    {result.properties.map((ps) => (
                      <th
                        key={ps.property_id}
                        className="px-3 py-2 font-medium text-center"
                      >
                        <div className="truncate max-w-32">
                          {ps.address?.split(",")[0] ||
                            ps.property_id.slice(0, 8)}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {CATEGORIES.map((cat) => (
                    <tr key={cat}>
                      <td className="px-3 py-2 font-medium capitalize text-gray-700">
                        {cat}
                        <span className="text-xs text-gray-400 ml-1">
                          (
                          {Math.round(
                            (result.weights_used[cat] || 0) * 100
                          )}
                          %)
                        </span>
                      </td>
                      {result.properties.map((ps) => {
                        const score = ps.category_scores[cat] ?? 50;
                        return (
                          <td
                            key={ps.property_id}
                            className="px-3 py-2 text-center"
                          >
                            <div className="flex flex-col items-center">
                              <span className="font-medium text-gray-900">
                                {formatScore(score)}
                              </span>
                              {/* Mini bar */}
                              <div className="w-16 h-1.5 bg-gray-100 rounded-full mt-1">
                                <div
                                  className="h-full bg-blue-500 rounded-full"
                                  style={{ width: `${score}%` }}
                                />
                              </div>
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  {/* Total row */}
                  <tr className="bg-gray-50 font-semibold">
                    <td className="px-3 py-2 text-gray-900">Total</td>
                    {result.properties.map((ps) => (
                      <td
                        key={ps.property_id}
                        className="px-3 py-2 text-center text-blue-600"
                      >
                        {formatScore(ps.total_score)}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
