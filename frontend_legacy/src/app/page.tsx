"use client";

/**
 * Dashboard — stats bar, watchlist kanban, active pipeline runs, add property button.
 */

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import Badge, { stageBadgeVariant } from "@/components/common/Badge";
import AddPropertyModal from "@/components/property/AddPropertyModal";
import type {
  PropertySummary,
  WatchlistEntry,
  AlertEvent,
  PipelineRunDetail,
} from "@/types/property";

const STAGES = [
  "researching",
  "touring",
  "offer",
  "contract",
  "closed",
  "rejected",
] as const;

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function pursueSignalBadge(decision?: Record<string, unknown>): {
  label: string;
  variant: "success" | "warning" | "critical" | "muted";
} {
  if (!decision) return { label: "No signal", variant: "muted" };
  const status = (decision.decision_status as string) || "";
  switch (status) {
    case "pursue":
      return { label: "Pursue", variant: "success" };
    case "maybe":
      return { label: "Maybe", variant: "warning" };
    case "pass":
      return { label: "Pass", variant: "critical" };
    default:
      return { label: status || "Unknown", variant: "muted" };
  }
}

export default function Dashboard() {
  const [properties, setProperties] = useState<PropertySummary[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [activeRuns, setActiveRuns] = useState<PipelineRunDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);

  const load = useCallback(async () => {
    try {
      const [props, watch, alertData] = await Promise.all([
        api.listProperties(),
        api.listWatchlist(),
        api.listAlerts({ unread_only: true, limit: 10 }),
      ]);
      setProperties(props);
      setWatchlist(watch);
      setAlerts(alertData);

      // Try to find active runs across properties
      const runs: PipelineRunDetail[] = [];
      for (const p of props.slice(0, 10)) {
        try {
          const pipeRuns = await api.getPipelineRuns(p.id, 1);
          const running = pipeRuns.filter(
            (r) => r.status === "running" || r.status === "queued"
          );
          runs.push(...running);
        } catch {
          // Property may not have runs
        }
      }
      setActiveRuns(runs);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const propMap = new Map<string, PropertySummary>();
  for (const p of properties) {
    propMap.set(p.id, p);
  }

  const byStage = new Map<string, WatchlistEntry[]>();
  for (const stage of STAGES) {
    byStage.set(stage, []);
  }
  for (const entry of watchlist) {
    const list = byStage.get(entry.stage);
    if (list) {
      list.push(entry);
    }
  }

  const totalTracked = properties.length;
  const onWatchlist = watchlist.length;
  const unreadAlerts = alerts.filter((a) => !a.is_read).length;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1">Dashboard</h1>
          <p className="text-gray-500 text-sm">
            Property Intelligence Platform -- Fairfax & Loudoun County, VA
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="px-4 py-2 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
        >
          + Add Property
        </button>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Properties" value={String(totalTracked)} />
        <StatCard label="On Watchlist" value={String(onWatchlist)} />
        <StatCard label="Active Runs" value={String(activeRuns.length)} />
        <StatCard
          label="Unread Alerts"
          value={String(unreadAlerts)}
          href="/alerts"
        />
      </div>

      {/* Active pipeline runs */}
      {activeRuns.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Active Pipeline Runs
          </h2>
          <div className="space-y-2">
            {activeRuns.map((run) => {
              const prop = propMap.get(run.property_id);
              const tasks = run.tasks || [];
              const completed = tasks.filter(
                (t) =>
                  t.status === "succeeded" || t.status === "failed"
              ).length;
              return (
                <a
                  key={run.id}
                  href={`/properties/${run.property_id}`}
                  className="block bg-white border border-blue-200 rounded-lg p-3 hover:bg-blue-50/50"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-2.5 h-2.5 bg-blue-500 rounded-full animate-pulse" />
                      <span className="text-sm font-medium text-gray-900">
                        {prop?.address || run.property_id.slice(0, 8)}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500">
                      {completed}/{tasks.length} tasks
                    </span>
                  </div>
                  <div className="mt-1.5 w-full bg-gray-100 rounded-full h-1.5">
                    <div
                      className="bg-blue-500 h-1.5 rounded-full transition-all"
                      style={{
                        width: `${tasks.length > 0 ? (completed / tasks.length) * 100 : 0}%`,
                      }}
                    />
                  </div>
                </a>
              );
            })}
          </div>
        </div>
      )}

      {/* Kanban board */}
      <h2 className="text-sm font-semibold text-gray-700 mb-3">
        Watchlist Pipeline
      </h2>
      {loading ? (
        <div className="text-gray-500 text-sm">Loading...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {STAGES.map((stage) => {
            const entries = byStage.get(stage) || [];
            return (
              <div
                key={stage}
                className="bg-white rounded-lg border border-gray-200 p-4 min-h-[200px]"
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-sm text-gray-500 uppercase tracking-wide">
                    {stage}
                  </h3>
                  {entries.length > 0 && (
                    <span className="text-xs text-gray-400 bg-gray-100 rounded-full px-2 py-0.5">
                      {entries.length}
                    </span>
                  )}
                </div>
                {entries.length === 0 ? (
                  <p className="text-gray-400 text-sm">No properties</p>
                ) : (
                  <div className="space-y-2">
                    {entries.map((entry) => {
                      const prop = propMap.get(entry.property_id);
                      return (
                        <a
                          key={entry.id}
                          href={`/properties/${entry.property_id}`}
                          className="block p-2 border border-gray-100 rounded hover:border-blue-200 hover:bg-blue-50/50 transition-colors"
                        >
                          <div className="text-xs font-medium text-gray-900 truncate">
                            {prop?.address || "Unknown"}
                          </div>
                          <div className="flex items-center justify-between mt-1">
                            {prop?.county && (
                              <Badge
                                label={prop.county}
                                variant={
                                  prop.county === "fairfax"
                                    ? "info"
                                    : "warning"
                                }
                                size="sm"
                              />
                            )}
                            <span className="text-xs text-gray-400">
                              {formatDate(entry.added_at)}
                            </span>
                          </div>
                        </a>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Add property modal */}
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

function StatCard({
  label,
  value,
  href,
}: {
  label: string;
  value: string;
  href?: string;
}) {
  const content = (
    <div className="bg-white border border-gray-200 rounded-lg p-4 hover:border-gray-300 transition-colors">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-2xl font-bold text-gray-900">{value}</div>
    </div>
  );

  if (href) {
    return <a href={href}>{content}</a>;
  }
  return content;
}
