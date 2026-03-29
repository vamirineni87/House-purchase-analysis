"use client";

/**
 * Alerts feed — chronological list with severity badges and mark-read.
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Badge, { severityBadgeVariant } from "@/components/common/Badge";
import type { AlertEvent } from "@/types/property";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function alertTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    price_cut: "Price Cut",
    status_change: "Status Change",
    back_on_market: "Back on Market",
    source_degraded: "Source Issue",
    nearby_price_change: "Nearby Change",
    price_threshold_exceeded: "Budget Alert",
    high_dom: "High DOM",
    significant_price_drop: "Big Price Drop",
    new_listing: "New Listing",
    pipeline_failed: "Pipeline Failed",
    data_stale: "Data Stale",
    comp_update: "Comp Update",
  };
  return labels[type] || type.replace(/_/g, " ");
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUnreadOnly, setShowUnreadOnly] = useState(false);

  async function loadAlerts() {
    setLoading(true);
    try {
      const data = await api.listAlerts({
        unread_only: showUnreadOnly,
        limit: 100,
      });
      setAlerts(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAlerts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showUnreadOnly]);

  async function handleMarkRead(alertId: string) {
    try {
      const updated = await api.markAlertRead(alertId, true);
      setAlerts((prev) =>
        prev.map((a) => (a.id === updated.id ? updated : a))
      );
    } catch {
      // silent
    }
  }

  async function handleMarkAllRead() {
    try {
      await api.markAllAlertsRead();
      setAlerts((prev) => prev.map((a) => ({ ...a, is_read: true })));
    } catch {
      // silent
    }
  }

  const unreadCount = alerts.filter((a) => !a.is_read).length;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Alerts</h1>
          {unreadCount > 0 && (
            <p className="text-sm text-gray-500 mt-1">
              {unreadCount} unread alert{unreadCount !== 1 ? "s" : ""}
            </p>
          )}
        </div>
        <div className="flex gap-3 items-center">
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={showUnreadOnly}
              onChange={(e) => setShowUnreadOnly(e.target.checked)}
              className="rounded border-gray-300 text-blue-600"
            />
            Unread only
          </label>
          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllRead}
              className="text-sm text-blue-600 hover:text-blue-800"
            >
              Mark all read
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="text-gray-500 text-sm">Loading alerts...</div>
      ) : alerts.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-1">No alerts</p>
          <p className="text-sm">
            Alerts will appear here when property changes are detected.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className={`bg-white border rounded-lg p-4 transition-colors ${
                alert.is_read
                  ? "border-gray-200"
                  : "border-blue-200 bg-blue-50/30"
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <Badge
                      label={alert.severity}
                      variant={severityBadgeVariant(alert.severity)}
                    />
                    <Badge
                      label={alertTypeLabel(alert.alert_type)}
                      variant="muted"
                    />
                    {!alert.is_read && (
                      <span className="w-2 h-2 bg-blue-500 rounded-full" />
                    )}
                  </div>
                  <h3 className="text-sm font-medium text-gray-900">
                    {alert.title}
                  </h3>
                  {alert.description && (
                    <p className="text-xs text-gray-600 mt-1">
                      {alert.description}
                    </p>
                  )}
                  <div className="text-xs text-gray-400 mt-2">
                    {formatDateTime(alert.triggered_at)}
                    {alert.property_id && (
                      <span className="ml-2">
                        <a
                          href={`/properties/${alert.property_id}`}
                          className="text-blue-500 hover:text-blue-700"
                        >
                          View property
                        </a>
                      </span>
                    )}
                  </div>
                </div>
                {!alert.is_read && (
                  <button
                    onClick={() => handleMarkRead(alert.id)}
                    className="text-xs text-gray-400 hover:text-gray-600 whitespace-nowrap"
                  >
                    Mark read
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
