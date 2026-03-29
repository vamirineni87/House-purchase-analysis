"use client";

/**
 * Dashboard page with kanban board.
 * Shows properties organized by watchlist stage.
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Badge, { stageBadgeVariant } from "@/components/common/Badge";
import type { PropertySummary, WatchlistEntry } from "@/types/property";

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

export default function Dashboard() {
  const [properties, setProperties] = useState<PropertySummary[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [props, watch] = await Promise.all([
          api.listProperties(),
          api.listWatchlist(),
        ]);
        setProperties(props);
        setWatchlist(watch);
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Build a map: property_id -> PropertySummary
  const propMap = new Map<string, PropertySummary>();
  for (const p of properties) {
    propMap.set(p.id, p);
  }

  // Group watchlist entries by stage
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

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Dashboard</h1>
      <p className="text-gray-500 text-sm mb-6">
        Property Intelligence Platform — Fairfax & Loudoun County, VA
      </p>

      {/* Stats bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Properties" value={String(totalTracked)} />
        <StatCard label="On Watchlist" value={String(onWatchlist)} />
        <StatCard
          label="Active Research"
          value={String(byStage.get("researching")?.length || 0)}
        />
        <StatCard
          label="In Offer/Contract"
          value={String(
            (byStage.get("offer")?.length || 0) +
              (byStage.get("contract")?.length || 0)
          )}
        />
      </div>

      {/* Kanban board */}
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
                  <h2 className="font-semibold text-sm text-gray-500 uppercase tracking-wide">
                    {stage}
                  </h2>
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
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-2xl font-bold text-gray-900">{value}</div>
    </div>
  );
}
