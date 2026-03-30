"use client";

/**
 * Property list page — table with address, price, county, status, pursue signal,
 * DOM, last run status. Click row navigates to detail page.
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Badge from "@/components/common/Badge";
import AddPropertyModal from "@/components/property/AddPropertyModal";
import type { PropertySummary, PipelineRunDetail } from "@/types/property";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatPropertyType(type: string): string {
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function runStatusBadge(
  status?: string
): { label: string; variant: "success" | "critical" | "warning" | "info" | "muted" } {
  if (!status) return { label: "No runs", variant: "muted" };
  switch (status) {
    case "succeeded":
      return { label: "Succeeded", variant: "success" };
    case "failed":
      return { label: "Failed", variant: "critical" };
    case "partial_success":
      return { label: "Partial", variant: "warning" };
    case "running":
      return { label: "Running", variant: "info" };
    default:
      return { label: status, variant: "muted" };
  }
}

export default function PropertiesPage() {
  const [properties, setProperties] = useState<PropertySummary[]>([]);
  const [latestRuns, setLatestRuns] = useState<
    Record<string, PipelineRunDetail>
  >({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);

  async function loadProperties() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listProperties();
      setProperties(data);

      // Load latest run for each property (first 20)
      const runMap: Record<string, PipelineRunDetail> = {};
      await Promise.allSettled(
        data.slice(0, 20).map(async (p) => {
          try {
            const runs = await api.getPipelineRuns(p.id, 1);
            if (runs.length > 0) {
              runMap[p.id] = runs[0];
            }
          } catch {
            // skip
          }
        })
      );
      setLatestRuns(runMap);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load properties"
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProperties();
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Properties</h1>
        <button
          onClick={() => setShowAddModal(true)}
          className="px-4 py-2 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
        >
          + Add Property
        </button>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 rounded px-3 py-2 mb-4">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-gray-500 text-sm">Loading properties...</div>
      ) : properties.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-2">No properties yet</p>
          <p className="text-sm">
            Click &quot;+ Add Property&quot; to start tracking.
          </p>
        </div>
      ) : (
        <>
          {/* Mobile card view */}
          <div className="md:hidden space-y-3">
            {properties.map((p) => {
              const run = latestRuns[p.id];
              const runBadge = runStatusBadge(run?.status);
              return (
                <a
                  key={p.id}
                  href={`/properties/${p.id}`}
                  className="block bg-white border border-gray-200 rounded-lg p-4 hover:border-blue-300 transition-colors"
                >
                  <div className="text-sm font-medium text-gray-900 mb-1">
                    {p.address || "No address"}
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {p.county && (
                      <Badge
                        label={p.county}
                        variant={
                          p.county === "fairfax" ? "info" : "warning"
                        }
                        size="sm"
                      />
                    )}
                    <Badge
                      label={runBadge.label}
                      variant={runBadge.variant}
                      size="sm"
                    />
                    <span className="text-xs text-gray-500 ml-auto">
                      {formatDate(p.created_at)}
                    </span>
                  </div>
                </a>
              );
            })}
          </div>

          {/* Desktop table view */}
          <div className="hidden md:block bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-gray-600 text-left">
                  <th className="px-4 py-3 font-medium">Address</th>
                  <th className="px-4 py-3 font-medium">County</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Last Run</th>
                  <th className="px-4 py-3 font-medium">Added</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {properties.map((p) => {
                  const run = latestRuns[p.id];
                  const runBadge = runStatusBadge(run?.status);
                  return (
                    <tr
                      key={p.id}
                      className="hover:bg-gray-50 cursor-pointer"
                      onClick={() =>
                        (window.location.href = `/properties/${p.id}`)
                      }
                    >
                      <td className="px-4 py-3 font-medium text-gray-900">
                        {p.address || "No address"}
                      </td>
                      <td className="px-4 py-3 text-gray-700 capitalize">
                        {p.county || "--"}
                      </td>
                      <td className="px-4 py-3 text-gray-700">
                        {formatPropertyType(p.property_type)}
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          label={runBadge.label}
                          variant={runBadge.variant}
                          size="sm"
                        />
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {formatDate(p.created_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      <AddPropertyModal
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
        onAdded={(propertyId) => {
          setShowAddModal(false);
          window.location.href = `/properties/${propertyId}`;
        }}
      />
    </div>
  );
}
