/**
 * API client for PIPA backend.
 * Uses Next.js rewrites to proxy /api/* to FastAPI backend.
 */

import type {
  AlertEvent,
  ComparisonRequest,
  ComparisonResult,
  CountyData,
  FinancialAnalysisRequest,
  FinancialAnalysisResult,
  PropertyNote,
  PropertySummary,
  Property,
  WatchlistEntry,
} from "@/types/property";

const BASE_URL = "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  // Properties
  listProperties: () => request<PropertySummary[]>("/properties"),
  getProperty: (id: string) => request<Property>(`/properties/${id}`),
  createProperty: (data: {
    address: {
      street: string;
      city: string;
      state: string;
      zip_code: string;
    };
    property_type: string;
  }) =>
    request<Property>("/properties", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteProperty: (id: string) =>
    request<void>(`/properties/${id}`, { method: "DELETE" }),

  // Watchlist
  listWatchlist: (stage?: string) =>
    request<WatchlistEntry[]>(
      `/watchlist${stage ? `?stage=${stage}` : ""}`
    ),
  addToWatchlist: (data: {
    property_id: string;
    stage?: string;
    priority?: number;
  }) =>
    request<WatchlistEntry>("/watchlist", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateWatchlistStage: (id: string, stage: string) =>
    request<WatchlistEntry>(`/watchlist/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ stage }),
    }),
  removeFromWatchlist: (id: string) =>
    request<void>(`/watchlist/${id}`, { method: "DELETE" }),

  // Alerts
  listAlerts: (opts?: { unread_only?: boolean; property_id?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.unread_only) params.set("unread_only", "true");
    if (opts?.property_id) params.set("property_id", opts.property_id);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<AlertEvent[]>(`/alerts${qs ? `?${qs}` : ""}`);
  },
  markAlertRead: (alertId: string, isRead: boolean = true) =>
    request<AlertEvent>(`/alerts/${alertId}`, {
      method: "PATCH",
      body: JSON.stringify({ is_read: isRead }),
    }),
  markAllAlertsRead: () =>
    request<void>("/alerts/mark-all-read", { method: "POST" }),

  // Notes
  listNotes: (propertyId: string) =>
    request<PropertyNote[]>(`/properties/${propertyId}/notes`),
  createNote: (propertyId: string, data: { content: string; note_type: string }) =>
    request<PropertyNote>(`/properties/${propertyId}/notes`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteNote: (propertyId: string, noteId: string) =>
    request<void>(`/properties/${propertyId}/notes/${noteId}`, {
      method: "DELETE",
    }),

  // County data
  getCountyData: (propertyId: string) =>
    request<CountyData>(`/properties/${propertyId}/county`),
  getAssessments: (propertyId: string) =>
    request<CountyData["assessments"]>(
      `/properties/${propertyId}/county/assessments`
    ),
  getPermits: (propertyId: string) =>
    request<CountyData["permits"]>(
      `/properties/${propertyId}/county/permits`
    ),
  getDeeds: (propertyId: string) =>
    request<CountyData["deeds"]>(
      `/properties/${propertyId}/county/deeds`
    ),
  refreshCountyData: (propertyId: string) =>
    request<{ property_id: string; assessments_fetched: number; permits_fetched: number; deeds_fetched: number }>(
      `/properties/${propertyId}/county/refresh`,
      { method: "POST" }
    ),

  // Financial analysis
  runFinancialAnalysis: (propertyId: string, data: FinancialAnalysisRequest) =>
    request<FinancialAnalysisResult>(
      `/properties/${propertyId}/analysis/financial`,
      { method: "POST", body: JSON.stringify(data) }
    ),

  // Comparison
  compareProperties: (data: ComparisonRequest) =>
    request<ComparisonResult>("/comparison", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Health
  health: () => request<{ status: string; db: boolean }>("/../../health"),
};
