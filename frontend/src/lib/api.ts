/**
 * API client for PIPA backend.
 * Uses Next.js rewrites to proxy /api/* to FastAPI backend.
 */

import type {
  AlertEvent,
  ComparisonRequest,
  ComparisonResult,
  ConditionResult,
  CountyData,
  CrossReferenceConflict,
  DecisionCase,
  DecisionPacket,
  DeepCompResult,
  FinancialAnalysisRequest,
  FinancialAnalysisResult,
  FullAnalysisResult,
  MortgageRates,
  CountyTaxRate,
  PipelineRunDetail,
  PipelineTaskRun,
  Property,
  PropertyIngestResponse,
  PropertyNote,
  PropertySummary,
  QuickCompResult,
  Recommendation,
  SourceFreshness,
  StressTestResult,
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
  // ====================================================================
  // Properties
  // ====================================================================
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

  ingestProperty: (data: {
    url?: string;
    address?: { street: string; city: string; state: string; zip_code: string };
    property_type?: string;
  }) =>
    request<PropertyIngestResponse>("/properties/ingest", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // ====================================================================
  // Pipeline
  // ====================================================================
  runPipeline: (propertyId: string, runType: string = "full_pipeline") =>
    request<PipelineRunDetail>(
      `/properties/${propertyId}/pipeline/run`,
      {
        method: "POST",
        body: JSON.stringify({ run_type: runType, initiated_by: "user" }),
      }
    ),

  runTask: (propertyId: string, taskName: string) =>
    request<PipelineRunDetail>(
      `/properties/${propertyId}/pipeline/run-task`,
      {
        method: "POST",
        body: JSON.stringify({ task_name: taskName }),
      }
    ),

  cancelPipeline: (propertyId: string) =>
    request<PipelineRunDetail>(
      `/properties/${propertyId}/pipeline/cancel`,
      { method: "POST" }
    ),

  getPipelineRuns: (propertyId: string, limit: number = 10) =>
    request<PipelineRunDetail[]>(
      `/properties/${propertyId}/pipeline/runs?limit=${limit}`
    ),

  getPipelineRun: (runId: string) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}`),

  rerunTask: (runId: string, taskName: string) =>
    request<PipelineTaskRun>(`/pipeline-runs/${runId}/rerun-task`, {
      method: "POST",
      body: JSON.stringify({ task_name: taskName }),
    }),

  // ====================================================================
  // Watchlist
  // ====================================================================
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

  // ====================================================================
  // Analysis
  // ====================================================================
  runFinancialAnalysis: (
    propertyId: string,
    data: FinancialAnalysisRequest
  ) =>
    request<FinancialAnalysisResult>(
      `/properties/${propertyId}/analysis/financial`,
      { method: "POST", body: JSON.stringify(data) }
    ),

  runConditionAnalysis: (propertyId: string) =>
    request<ConditionResult>(
      `/properties/${propertyId}/analysis/condition`,
      { method: "POST" }
    ),

  runOfferAnalysis: (propertyId: string, data: Record<string, unknown>) =>
    request<Record<string, unknown>>(
      `/properties/${propertyId}/analysis/offer`,
      { method: "POST", body: JSON.stringify(data) }
    ),

  runStressTest: (propertyId: string, data: Record<string, unknown>) =>
    request<StressTestResult>(
      `/properties/${propertyId}/analysis/stress`,
      { method: "POST", body: JSON.stringify(data) }
    ),

  runFullAnalysis: (propertyId: string, data: Record<string, unknown>) =>
    request<FullAnalysisResult>(
      `/properties/${propertyId}/analysis/full`,
      { method: "POST", body: JSON.stringify(data) }
    ),

  // ====================================================================
  // Comps
  // ====================================================================
  runCompsQuick: (propertyId: string) =>
    request<QuickCompResult>(
      `/properties/${propertyId}/comps/quick`,
      { method: "POST" }
    ),

  runCompsDeep: (propertyId: string) =>
    request<DeepCompResult>(
      `/properties/${propertyId}/comps/deep`,
      { method: "POST" }
    ),

  getComps: (propertyId: string) =>
    request<{ quick_comp?: QuickCompResult; deep_comp?: DeepCompResult }>(
      `/properties/${propertyId}/comps`
    ),

  // ====================================================================
  // Refresh
  // ====================================================================
  refreshAll: (propertyId: string) =>
    request<Record<string, unknown>>(
      `/properties/${propertyId}/refresh`,
      { method: "POST" }
    ),

  refreshSource: (propertyId: string, source: string) =>
    request<Record<string, unknown>>(
      `/properties/${propertyId}/refresh/${source}`,
      { method: "POST" }
    ),

  getFreshness: (propertyId: string) =>
    request<SourceFreshness[]>(`/properties/${propertyId}/freshness`),

  crossReference: (propertyId: string) =>
    request<CrossReferenceConflict[]>(
      `/properties/${propertyId}/cross-reference`
    ),

  // ====================================================================
  // Decision
  // ====================================================================
  getDecision: (propertyId: string) =>
    request<DecisionCase>(`/properties/${propertyId}/decision`),

  createDecision: (propertyId: string) =>
    request<DecisionCase>(`/properties/${propertyId}/decision`, {
      method: "POST",
    }),

  updateDecision: (propertyId: string, data: Record<string, unknown>) =>
    request<DecisionCase>(`/properties/${propertyId}/decision`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getDecisionPacket: (propertyId: string) =>
    request<DecisionPacket>(`/properties/${propertyId}/decision/packet`),

  getRecommendations: (propertyId: string) =>
    request<Recommendation[]>(
      `/properties/${propertyId}/decision/recommendations`
    ),

  // ====================================================================
  // County
  // ====================================================================
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
    request<{
      property_id: string;
      assessments_fetched: number;
      permits_fetched: number;
      deeds_fetched: number;
    }>(`/properties/${propertyId}/county/refresh`, { method: "POST" }),

  // ====================================================================
  // Notes
  // ====================================================================
  listNotes: (propertyId: string) =>
    request<PropertyNote[]>(`/properties/${propertyId}/notes`),

  createNote: (
    propertyId: string,
    data: { content: string; note_type: string }
  ) =>
    request<PropertyNote>(`/properties/${propertyId}/notes`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deleteNote: (propertyId: string, noteId: string) =>
    request<void>(`/properties/${propertyId}/notes/${noteId}`, {
      method: "DELETE",
    }),

  // ====================================================================
  // Alerts
  // ====================================================================
  listAlerts: (opts?: {
    unread_only?: boolean;
    property_id?: string;
    limit?: number;
  }) => {
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

  // ====================================================================
  // Comparison
  // ====================================================================
  compareProperties: (data: ComparisonRequest) =>
    request<ComparisonResult>("/comparison", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // ====================================================================
  // Rates
  // ====================================================================
  getMortgageRates: () => request<MortgageRates>("/rates/mortgage"),

  getTaxRate: (county: string) =>
    request<CountyTaxRate>(`/rates/tax/${county}`),

  // ====================================================================
  // Health
  // ====================================================================
  health: () => request<{ status: string; db: boolean }>("/../../health"),
};
