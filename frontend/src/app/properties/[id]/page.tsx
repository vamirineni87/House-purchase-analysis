"use client";

/**
 * Property detail page — THE most important page.
 *
 * Header: address, price, pursue badge, stage selector, pipeline ribbon, action buttons.
 * 10 tabs: Summary, Pipeline, Financial, Value/Comps, Condition,
 *          County, Listing History, Schools, AI Analysis, Notes.
 */

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import Badge, { stageBadgeVariant } from "@/components/common/Badge";
import PipelineStatusRibbon from "@/components/pipeline/PipelineStatusRibbon";
import TaskStatusList from "@/components/pipeline/TaskStatusList";
import PriceBenchmarks from "@/components/analysis/PriceBenchmarks";
import FinancialPanel from "@/components/analysis/FinancialPanel";
import ConditionPanel from "@/components/analysis/ConditionPanel";
import SchoolPanel from "@/components/analysis/SchoolPanel";
import type {
  Property,
  WatchlistEntry,
  WatchlistStage,
  CountyData,
  PropertyNote,
  PipelineRunDetail,
  DecisionPacket,
  DecisionCase,
  QuickCompResult,
  DeepCompResult,
  ConditionResult,
  ComponentInfo,
  SchoolInfo,
  ListingHistory,
  SourceFreshness,
} from "@/types/property";

// =====================================================================
// Constants
// =====================================================================

const TABS = [
  "Summary",
  "Pipeline",
  "Financial",
  "Value/Comps",
  "Condition",
  "County",
  "Listing History",
  "Schools",
  "AI Analysis",
  "Notes",
] as const;
type Tab = (typeof TABS)[number];

const STAGES: WatchlistStage[] = [
  "researching",
  "touring",
  "offer",
  "contract",
  "closed",
  "rejected",
];

// =====================================================================
// Helpers
// =====================================================================

function formatCurrency(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

function formatDate(iso: string | undefined): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function pursueVariant(
  status?: string
): "success" | "warning" | "critical" | "muted" {
  switch (status) {
    case "pursue":
      return "success";
    case "maybe":
      return "warning";
    case "pass":
      return "critical";
    default:
      return "muted";
  }
}

// =====================================================================
// Main Component
// =====================================================================

export default function PropertyDetailPage() {
  const params = useParams();
  const propertyId = params.id as string;

  // Core state
  const [property, setProperty] = useState<Property | null>(null);
  const [watchEntry, setWatchEntry] = useState<WatchlistEntry | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("Summary");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Pipeline state
  const [pipelineRuns, setPipelineRuns] = useState<PipelineRunDetail[]>([]);
  const [latestRun, setLatestRun] = useState<PipelineRunDetail | null>(null);

  // Decision state
  const [decision, setDecision] = useState<DecisionCase | null>(null);
  const [packet, setPacket] = useState<DecisionPacket | null>(null);

  // Comp state
  const [quickComp, setQuickComp] = useState<QuickCompResult | null>(null);
  const [deepComp, setDeepComp] = useState<DeepCompResult | null>(null);

  // Condition state
  const [conditionResult, setConditionResult] =
    useState<ConditionResult | null>(null);
  const [components, setComponents] = useState<ComponentInfo[]>([]);

  // County state
  const [countyData, setCountyData] = useState<CountyData | null>(null);
  const [countyLoading, setCountyLoading] = useState(false);

  // School state
  const [schools, setSchools] = useState<SchoolInfo[]>([]);

  // Notes state
  const [notes, setNotes] = useState<PropertyNote[]>([]);
  const [newNoteContent, setNewNoteContent] = useState("");
  const [newNoteType, setNewNoteType] = useState("general");
  const [notesLoading, setNotesLoading] = useState(false);

  // Listing data (scraped from Zillow/Redfin)
  const [listingData, setListingData] = useState<Record<string, unknown> | null>(null);

  // Analysis results from pipeline
  const [analysisResults, setAnalysisResults] = useState<Record<string, unknown>>({});

  // Freshness
  const [freshness, setFreshness] = useState<SourceFreshness[]>([]);

  // ===================================================================
  // Load core data
  // ===================================================================

  const loadCore = useCallback(async () => {
    setLoading(true);
    try {
      const [prop, watchlist] = await Promise.all([
        api.getProperty(propertyId),
        api.listWatchlist(),
      ]);
      setProperty(prop);
      const entry = watchlist.find((w) => w.property_id === propertyId);
      setWatchEntry(entry || null);

      // Load pipeline runs
      try {
        const runs = await api.getPipelineRuns(propertyId, 10);
        setPipelineRuns(runs);
        if (runs.length > 0) setLatestRun(runs[0]);
      } catch {
        // no runs yet
      }

      // Load listing data (scraped Zillow/Redfin data)
      try {
        const ld = await api.getListingData(propertyId);
        if (ld.listing_data) {
          setListingData(ld.listing_data);
        }
      } catch {
        // no listing data yet
      }

      // Load analysis results
      try {
        const ar = await api.getAnalysisResults(propertyId);
        setAnalysisResults(ar.analyses || {});
      } catch {
        // no analysis results yet
      }

      // Load decision case
      try {
        const dec = await api.getDecision(propertyId);
        setDecision(dec);
      } catch {
        // no decision yet
      }

      // Load decision packet
      try {
        const pkt = await api.getDecisionPacket(propertyId);
        setPacket(pkt);
      } catch {
        // no packet yet
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load property"
      );
    } finally {
      setLoading(false);
    }
  }, [propertyId]);

  useEffect(() => {
    loadCore();
  }, [loadCore]);

  // ===================================================================
  // Lazy load tab data
  // ===================================================================

  useEffect(() => {
    if (activeTab === "County" && !countyData && !countyLoading) {
      setCountyLoading(true);
      api
        .getCountyData(propertyId)
        .then(setCountyData)
        .catch(() => {})
        .finally(() => setCountyLoading(false));
    }
  }, [activeTab, propertyId, countyData, countyLoading]);

  useEffect(() => {
    if (activeTab === "Notes") {
      loadNotes();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, propertyId]);

  useEffect(() => {
    if (activeTab === "Value/Comps" && !quickComp && !deepComp) {
      api
        .getComps(propertyId)
        .then((data) => {
          if (data.quick_comp) setQuickComp(data.quick_comp);
          if (data.deep_comp) setDeepComp(data.deep_comp);
        })
        .catch(() => {});
    }
  }, [activeTab, propertyId, quickComp, deepComp]);

  useEffect(() => {
    if (activeTab === "Pipeline") {
      api
        .getFreshness(propertyId)
        .then(setFreshness)
        .catch(() => {});
    }
  }, [activeTab, propertyId]);

  // ===================================================================
  // Actions
  // ===================================================================

  async function handleRunPipeline() {
    setActionLoading("pipeline");
    try {
      const run = await api.runPipeline(propertyId, "full_pipeline");
      setLatestRun(run);
      setPipelineRuns((prev) => [run, ...prev]);
    } catch {
      // silent
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRefreshListing() {
    setActionLoading("refresh_listing");
    try {
      await api.refreshSource(propertyId, "zillow");
    } catch {
      // silent
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRefreshCounty() {
    setActionLoading("refresh_county");
    try {
      await api.refreshCountyData(propertyId);
      // Reload county data
      const data = await api.getCountyData(propertyId);
      setCountyData(data);
    } catch {
      // silent
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRunDeepComp() {
    setActionLoading("deep_comp");
    try {
      const result = await api.runCompsDeep(propertyId);
      setDeepComp(result);
    } catch (err) {
      console.error("Deep comp failed:", err);
      alert("Deep comp failed: " + (err instanceof Error ? err.message : "unknown error"));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRerunAI() {
    setActionLoading("rerun_ai");
    try {
      const run = await api.runPipeline(propertyId, "rerun_ai");
      setLatestRun(run);
      setPipelineRuns((prev) => [run, ...prev]);
    } catch {
      // silent
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRetryFailed() {
    if (!latestRun) return;
    setActionLoading("retry");
    const failedTasks = (latestRun.tasks || []).filter(
      (t) => t.status === "failed"
    );
    for (const task of failedTasks) {
      try {
        await api.rerunTask(latestRun.id, task.task_name);
      } catch {
        // continue
      }
    }
    // Reload
    try {
      const runs = await api.getPipelineRuns(propertyId, 10);
      setPipelineRuns(runs);
      if (runs.length > 0) setLatestRun(runs[0]);
    } catch {
      // silent
    }
    setActionLoading(null);
  }

  async function handleStageChange(stage: string) {
    try {
      if (watchEntry) {
        const updated = await api.updateWatchlistStage(watchEntry.id, stage);
        setWatchEntry(updated);
      } else {
        const entry = await api.addToWatchlist({
          property_id: propertyId,
          stage,
        });
        setWatchEntry(entry);
      }
    } catch {
      // silent
    }
  }

  async function loadNotes() {
    setNotesLoading(true);
    try {
      const data = await api.listNotes(propertyId);
      setNotes(data);
    } catch {
      // silent
    } finally {
      setNotesLoading(false);
    }
  }

  async function handleAddNote() {
    if (!newNoteContent.trim()) return;
    try {
      await api.createNote(propertyId, {
        content: newNoteContent.trim(),
        note_type: newNoteType,
      });
      setNewNoteContent("");
      loadNotes();
    } catch {
      // silent
    }
  }

  async function handleDeleteNote(noteId: string) {
    try {
      await api.deleteNote(propertyId, noteId);
      setNotes((prev) => prev.filter((n) => n.id !== noteId));
    } catch {
      // silent
    }
  }

  async function handleRerunTask(taskName: string) {
    if (!latestRun) return;
    setActionLoading(taskName);
    try {
      await api.rerunTask(latestRun.id, taskName);
      const runs = await api.getPipelineRuns(propertyId, 10);
      setPipelineRuns(runs);
      if (runs.length > 0) setLatestRun(runs[0]);
    } catch {
      // silent
    } finally {
      setActionLoading(null);
    }
  }

  // ===================================================================
  // Render
  // ===================================================================

  if (loading) {
    return <div className="text-gray-500 text-sm">Loading property...</div>;
  }

  if (error || !property) {
    return (
      <div className="text-red-600 text-sm">
        {error || "Property not found"}
      </div>
    );
  }

  const currentAddress = property.addresses.find(
    (a) => a.is_current && a.address_type === "situs"
  );

  // Extract parsed fields from pipeline data if available
  // Get listing data from the scraped Zillow/Redfin data
  const ld = listingData || {};
  const listPrice =
    (ld.price as number) ||
    packet?.price_view?.list_price ||
    undefined;

  return (
    <div>
      {/* ============================================================ */}
      {/* HEADER */}
      {/* ============================================================ */}
      <div className="mb-4">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {currentAddress?.normalized_address || "No address"}
            </h1>
            <div className="flex items-center gap-3 mt-1 text-sm text-gray-500 flex-wrap">
              {listPrice && (
                <span className="text-lg font-bold text-gray-900">
                  {formatCurrency(listPrice)}
                </span>
              )}
              {decision && (
                <Badge
                  label={
                    decision.decision_status.charAt(0).toUpperCase() +
                    decision.decision_status.slice(1)
                  }
                  variant={pursueVariant(decision.decision_status)}
                  size="md"
                />
              )}
              {currentAddress?.county && (
                <Badge
                  label={
                    currentAddress.county.charAt(0).toUpperCase() +
                    currentAddress.county.slice(1) +
                    " County"
                  }
                  variant="info"
                />
              )}
              <span className="capitalize">
                {property.property_type.replace(/_/g, " ")}
              </span>
            </div>
          </div>

          {/* Stage selector */}
          <div className="flex items-center gap-2">
            {watchEntry && (
              <Badge
                label={watchEntry.stage}
                variant={stageBadgeVariant(watchEntry.stage)}
                size="md"
              />
            )}
            <select
              value={watchEntry?.stage || ""}
              onChange={(e) => handleStageChange(e.target.value)}
              className="text-sm border border-gray-300 rounded px-2 py-1"
            >
              <option value="" disabled>
                {watchEntry ? "Move to..." : "Add to watchlist"}
              </option>
              {STAGES.map((s) => (
                <option key={s} value={s}>
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Pipeline status ribbon */}
      <div className="mb-4">
        <PipelineStatusRibbon
          latestRun={latestRun}
          onRetryFailed={handleRetryFailed}
          onRunPipeline={handleRunPipeline}
          loading={actionLoading !== null}
        />
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2 mb-6">
        <ActionButton
          label="Run Full Pipeline"
          onClick={handleRunPipeline}
          loading={actionLoading === "pipeline"}
          disabled={actionLoading !== null}
        />
        <ActionButton
          label="Refresh Listing"
          onClick={handleRefreshListing}
          loading={actionLoading === "refresh_listing"}
          disabled={actionLoading !== null}
          variant="secondary"
        />
        <ActionButton
          label="Refresh County"
          onClick={handleRefreshCounty}
          loading={actionLoading === "refresh_county"}
          disabled={actionLoading !== null}
          variant="secondary"
        />
        <ActionButton
          label="Run Deep Comp"
          onClick={handleRunDeepComp}
          loading={actionLoading === "deep_comp"}
          disabled={actionLoading !== null}
          variant="secondary"
        />
        <ActionButton
          label="Rerun AI"
          onClick={handleRerunAI}
          loading={actionLoading === "rerun_ai"}
          disabled={actionLoading !== null}
          variant="secondary"
        />
      </div>

      {/* ============================================================ */}
      {/* TABS */}
      {/* ============================================================ */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="flex gap-0 -mb-px overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab
                  ? "border-blue-500 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </div>

      {/* ============================================================ */}
      {/* TAB CONTENT */}
      {/* ============================================================ */}
      <div>
        {activeTab === "Summary" && (
          <SummaryTab
            property={property}
            watchEntry={watchEntry}
            packet={packet}
            decision={decision}
            listPrice={listPrice}
            latestRun={latestRun}
            listingData={ld}
          />
        )}
        {activeTab === "Pipeline" && (
          <PipelineTab
            runs={pipelineRuns}
            latestRun={latestRun}
            freshness={freshness}
            onRerunTask={handleRerunTask}
            rerunning={actionLoading}
          />
        )}
        {activeTab === "Financial" && (
          <FinancialPanel propertyId={propertyId} />
        )}
        {activeTab === "Value/Comps" && (
          <CompsTab
            quickComp={quickComp}
            deepComp={deepComp}
            propertyId={propertyId}
            onRunQuick={async () => {
              try {
                setActionLoading("quick_comp");
                const r = await api.runCompsQuick(propertyId);
                setQuickComp(r);
              } catch (err) {
                console.error("Quick comp failed:", err);
                alert("Quick comp failed: " + (err instanceof Error ? err.message : "unknown error"));
              } finally {
                setActionLoading(null);
              }
            }}
            onRunDeep={handleRunDeepComp}
            loading={
              actionLoading === "deep_comp" || actionLoading === "quick_comp"
            }
          />
        )}
        {activeTab === "Condition" && (
          <ConditionPanel
            conditionResult={conditionResult}
            components={components}
          />
        )}
        {activeTab === "County" && (
          <CountyTab
            data={countyData}
            loading={countyLoading}
            propertyId={propertyId}
            onRefresh={handleRefreshCounty}
            refreshing={actionLoading === "refresh_county"}
          />
        )}
        {activeTab === "Listing History" && (
          <ListingHistoryTab propertyId={propertyId} listingData={ld} />
        )}
        {activeTab === "Schools" && <SchoolsTab propertyId={propertyId} listingData={ld} />}
        {activeTab === "AI Analysis" && (
          <AIAnalysisTab packet={packet} propertyId={propertyId} />
        )}
        {activeTab === "Notes" && (
          <NotesTab
            notes={notes}
            loading={notesLoading}
            newContent={newNoteContent}
            newType={newNoteType}
            onContentChange={setNewNoteContent}
            onTypeChange={setNewNoteType}
            onAdd={handleAddNote}
            onDelete={handleDeleteNote}
          />
        )}
      </div>
    </div>
  );
}

// =====================================================================
// Action Button
// =====================================================================

function ActionButton({
  label,
  onClick,
  loading,
  disabled,
  variant = "primary",
}: {
  label: string;
  onClick: () => void;
  loading: boolean;
  disabled: boolean;
  variant?: "primary" | "secondary";
}) {
  const base =
    variant === "primary"
      ? "text-white bg-blue-600 hover:bg-blue-700"
      : "text-gray-700 bg-gray-100 hover:bg-gray-200";

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-1.5 text-xs font-medium rounded transition-colors disabled:opacity-50 ${base}`}
    >
      {loading ? "..." : label}
    </button>
  );
}

// =====================================================================
// Tab 1: Summary
// =====================================================================

function SummaryTab({
  property,
  watchEntry,
  packet,
  decision,
  listPrice,
  latestRun,
  listingData,
}: {
  property: Property;
  watchEntry: WatchlistEntry | null;
  packet: DecisionPacket | null;
  decision: DecisionCase | null;
  listPrice?: number;
  latestRun: PipelineRunDetail | null;
  listingData: Record<string, unknown>;
}) {
  // Use listing data from Zillow/Redfin scrape
  const ld = listingData || {};

  return (
    <div className="space-y-6">
      {/* Quick Take */}
      {packet?.quick_take && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Quick Take
          </h3>
          <div className="flex items-center gap-2 mb-2">
            <Badge
              label={packet.quick_take.recommendation.toUpperCase()}
              variant={pursueVariant(packet.quick_take.recommendation)}
              size="md"
            />
          </div>
          <ul className="space-y-1">
            {packet.quick_take.bullets.map((bullet, i) => (
              <li key={i} className="text-sm text-gray-700 flex gap-2">
                <span className="text-gray-400">-</span>
                {bullet}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Price Benchmarks */}
      <PriceBenchmarks
        askPrice={listPrice}
        zestimate={(ld.zestimate as number) || undefined}
        assessedValue={
          (ld.tax_assessed_value as number) || (ld.tax_assessed as number) ||
          packet?.price_view?.assessment_value || undefined
        }
        compEstimate={packet?.price_view?.comp_estimate || undefined}
      />

      {/* Key Metrics */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">
          Key Metrics
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            label="Beds"
            value={ld.bedrooms || ld.beds ? String(ld.bedrooms || ld.beds) : "--"}
          />
          <MetricCard
            label="Baths"
            value={ld.baths || ld.bathrooms ? String(ld.baths || ld.bathrooms) : "--"}
          />
          <MetricCard
            label="Sqft"
            value={
              ld.sqft
                ? Number(ld.sqft).toLocaleString()
                : "--"
            }
          />
          <MetricCard
            label="Lot"
            value={
              ld.lot_sqft
                ? Number(ld.lot_sqft).toLocaleString() + " sqft"
                : ld.lot_acres
                  ? String(ld.lot_acres) + " ac"
                  : "--"
            }
          />
          <MetricCard
            label="Year Built"
            value={
              ld.year_built ? String(ld.year_built) : "--"
            }
          />
          <MetricCard
            label="HOA"
            value={
              ld.hoa_monthly || ld.hoa
                ? formatCurrency(Number(ld.hoa_monthly || ld.hoa)) + "/mo"
                : "--"
            }
          />
          <MetricCard
            label="DOM"
            value={
              ld.days_on_zillow || ld.dom || ld.days_on_market
                ? String(ld.days_on_zillow || ld.dom || ld.days_on_market)
                : "--"
            }
          />
          <MetricCard
            label="CDOM"
            value={
              ld.cdom || ld.cumulative_dom
                ? String(ld.cdom || ld.cumulative_dom)
                : "--"
            }
          />
        </div>
      </div>

      {/* Red flags and strengths from AI */}
      {packet?.hidden_cost?.unknowns &&
        packet.hidden_cost.unknowns.length > 0 && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-red-700 mb-2">
              Red Flags
            </h3>
            <ul className="space-y-1">
              {packet.hidden_cost.unknowns.map((item, i) => (
                <li key={i} className="text-sm text-red-700 flex gap-2">
                  <span>!</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}

      {packet?.community_view?.community_notes &&
        packet.community_view.community_notes.length > 0 && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-green-700 mb-2">
              Strengths
            </h3>
            <ul className="space-y-1">
              {packet.community_view.community_notes.map((item, i) => (
                <li key={i} className="text-sm text-green-700 flex gap-2">
                  <span>+</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}

      {/* Address details */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">
          Address & Identifiers
        </h3>
        <div className="space-y-2">
          {property.addresses.map((addr) => (
            <div
              key={addr.id}
              className="flex items-center justify-between text-sm"
            >
              <span className="text-gray-900">
                {addr.normalized_address}
              </span>
              <div className="flex gap-2">
                <Badge label={addr.address_type} variant="muted" />
                {addr.is_current && (
                  <Badge label="current" variant="success" />
                )}
              </div>
            </div>
          ))}
        </div>
        {property.parcel_identifiers.length > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-100 space-y-2">
            {property.parcel_identifiers.map((pid) => (
              <div
                key={pid.id}
                className="flex items-center justify-between text-sm"
              >
                <span className="text-gray-900 font-mono">
                  {pid.identifier_value}
                </span>
                <div className="flex gap-2">
                  <Badge label={pid.identifier_type} variant="muted" />
                  <Badge label={pid.county} variant="info" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3">
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className="text-sm font-semibold text-gray-900">{value}</div>
    </div>
  );
}

// =====================================================================
// Tab 2: Pipeline / Data Health
// =====================================================================

function PipelineTab({
  runs,
  latestRun,
  freshness,
  onRerunTask,
  rerunning,
}: {
  runs: PipelineRunDetail[];
  latestRun: PipelineRunDetail | null;
  freshness: SourceFreshness[];
  onRerunTask: (taskName: string) => void;
  rerunning: string | null;
}) {
  return (
    <div className="space-y-6">
      {/* Freshness warnings */}
      {freshness.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Data Freshness
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {freshness.map((f) => (
              <div
                key={f.source}
                className={`border rounded-lg p-3 ${
                  f.is_stale
                    ? "border-amber-200 bg-amber-50"
                    : "border-gray-200 bg-white"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-900 capitalize">
                    {f.source}
                  </span>
                  {f.is_stale ? (
                    <Badge label="Stale" variant="warning" size="sm" />
                  ) : (
                    <Badge label="Fresh" variant="success" size="sm" />
                  )}
                </div>
                <div className="text-xs text-gray-500">
                  {f.last_fetched
                    ? `Last: ${formatDate(f.last_fetched)}`
                    : "Never fetched"}
                  {" | "}TTL: {f.ttl_hours}h
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Latest run tasks */}
      {latestRun && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Latest Run: {latestRun.run_type.replace(/_/g, " ")}
          </h3>
          <TaskStatusList
            tasks={latestRun.tasks || []}
            onRerunTask={onRerunTask}
            rerunning={rerunning}
          />
        </div>
      )}

      {/* Run history */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Run History
        </h3>
        {runs.length === 0 ? (
          <div className="text-sm text-gray-500">
            No pipeline runs yet. Click "Run Full Pipeline" to start.
          </div>
        ) : (
          <div className="space-y-2">
            {runs.map((run) => {
              const tasks = run.tasks || [];
              const succeeded = tasks.filter(
                (t) => t.status === "succeeded"
              ).length;
              const failed = tasks.filter(
                (t) => t.status === "failed"
              ).length;
              return (
                <div
                  key={run.id}
                  className="bg-white border border-gray-200 rounded-lg p-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge
                        label={run.status.replace(/_/g, " ")}
                        variant={
                          run.status === "succeeded"
                            ? "success"
                            : run.status === "failed"
                              ? "critical"
                              : run.status === "partial_success"
                                ? "warning"
                                : "info"
                        }
                        size="sm"
                      />
                      <span className="text-sm text-gray-700">
                        {run.run_type.replace(/_/g, " ")}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      <span>
                        {succeeded}/{tasks.length} ok
                        {failed > 0 && `, ${failed} failed`}
                      </span>
                      <span>{formatDate(run.created_at)}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// =====================================================================
// Tab 4: Value/Comps
// =====================================================================

function CompsTab({
  quickComp,
  deepComp,
  propertyId,
  onRunQuick,
  onRunDeep,
  loading,
}: {
  quickComp: QuickCompResult | null;
  deepComp: DeepCompResult | null;
  propertyId: string;
  onRunQuick: () => void;
  onRunDeep: () => void;
  loading: boolean;
}) {
  return (
    <div className="space-y-6">
      {/* Quick comp */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700">
            Quick Comp Analysis
          </h3>
          <button
            onClick={onRunQuick}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Running..." : "Run Quick Comp"}
          </button>
        </div>

        {quickComp ? (
          <div className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3">
              <div className="text-xs text-blue-700 font-medium">Quick Comp Results</div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard label="Confidence" value={quickComp.quick_confidence || "unknown"} />
              <MetricCard label="Ask vs Comps" value={quickComp.asking_vs_comps || "--"} />
              <MetricCard label="Sold Comps" value={String(quickComp.sold_count ?? 0)} />
              <MetricCard label="Active" value={String(quickComp.active_count ?? 0)} />
            </div>

            {quickComp.rough_value_band && (
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <h4 className="text-xs text-gray-500 mb-2">Value Band</h4>
                <div className="flex items-center gap-4 text-sm">
                  <span className="text-green-600 font-medium">
                    Low: {formatCurrency(quickComp.rough_value_band.low)}
                  </span>
                  <span className="text-blue-600 font-bold">
                    Mid: {formatCurrency(quickComp.rough_value_band.mid)}
                  </span>
                  <span className="text-red-600 font-medium">
                    High: {formatCurrency(quickComp.rough_value_band.high)}
                  </span>
                </div>
              </div>
            )}

            {quickComp.warnings.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <div className="text-xs text-amber-700 space-y-1">
                  {quickComp.warnings.map((w, i) => (
                    <div key={i}>! {w}</div>
                  ))}
                </div>
              </div>
            )}

            {quickComp.filtered_comps.length > 0 && (
              <div>
                <h4 className="text-xs text-gray-500 mb-2">
                  Top Comps ({quickComp.filtered_comps.length})
                </h4>
                <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr className="bg-gray-50 text-gray-600 text-left">
                        <th className="px-3 py-2 font-medium">Address</th>
                        <th className="px-3 py-2 font-medium text-right">Price</th>
                        <th className="px-3 py-2 font-medium text-right">Sqft</th>
                        <th className="px-3 py-2 font-medium">Status</th>
                        <th className="px-3 py-2 font-medium text-right">Score</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {quickComp.filtered_comps.map((c, i) => (
                        <tr key={i}>
                          <td className="px-3 py-2 text-gray-900 truncate max-w-48">
                            {c.address}
                          </td>
                          <td className="px-3 py-2 text-right">
                            {c.price ? formatCurrency(c.price) : "--"}
                          </td>
                          <td className="px-3 py-2 text-right">
                            {c.sqft?.toLocaleString() || "--"}
                          </td>
                          <td className="px-3 py-2">
                            <Badge
                              label={c.status}
                              variant={
                                c.status === "sold"
                                  ? "success"
                                  : c.status === "active"
                                    ? "info"
                                    : "warning"
                              }
                              size="sm"
                            />
                          </td>
                          <td className="px-3 py-2 text-right font-medium">
                            {c.similarity_score?.toFixed(0) || "--"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-sm text-gray-500 text-center py-6 bg-gray-50 rounded-lg">
            No quick comp data. Click "Run Quick Comp" to analyze.
          </div>
        )}
      </div>

      {/* Deep comp */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700">
            Deep Comp Analysis
          </h3>
          <button
            onClick={onRunDeep}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Running (~2 min)..." : "Run Deep Comp"}
          </button>
        </div>

        {deepComp ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard label="Confidence" value={deepComp.confidence} />
              <MetricCard
                label="Sold Comps"
                value={String(deepComp.sold_comps.length)}
              />
              <MetricCard
                label="Active"
                value={String(deepComp.active_listings.length)}
              />
              <MetricCard
                label="Conflicts"
                value={String(deepComp.conflicts.length)}
              />
            </div>

            {deepComp.value_range && (
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <h4 className="text-xs text-gray-500 mb-2">
                  Adjusted Value Range
                </h4>
                <div className="flex items-center gap-4 text-sm">
                  <span className="text-green-600 font-medium">
                    Low: {formatCurrency(deepComp.value_range.low)}
                  </span>
                  <span className="text-blue-600 font-bold">
                    Mid: {formatCurrency(deepComp.value_range.mid)}
                  </span>
                  <span className="text-red-600 font-medium">
                    High: {formatCurrency(deepComp.value_range.high)}
                  </span>
                </div>
              </div>
            )}

            {deepComp.sold_comps.length > 0 && (
              <div>
                <h4 className="text-xs text-gray-500 mb-2">
                  County-Verified Sold Comps
                </h4>
                <div className="bg-white border border-gray-200 rounded-lg overflow-hidden overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr className="bg-gray-50 text-gray-600 text-left">
                        <th className="px-3 py-2 font-medium">Address</th>
                        <th className="px-3 py-2 font-medium text-right">Sale Price</th>
                        <th className="px-3 py-2 font-medium">Date</th>
                        <th className="px-3 py-2 font-medium text-right">Sqft</th>
                        <th className="px-3 py-2 font-medium text-right">Beds</th>
                        <th className="px-3 py-2 font-medium text-right">Year</th>
                        <th className="px-3 py-2 font-medium">Conflict?</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {deepComp.sold_comps.map((c, i) => (
                        <tr key={i}>
                          <td className="px-3 py-2 text-gray-900 truncate max-w-40">
                            {c.address}
                          </td>
                          <td className="px-3 py-2 text-right font-medium">
                            {formatCurrency(c.sale_price)}
                          </td>
                          <td className="px-3 py-2">{c.sale_date}</td>
                          <td className="px-3 py-2 text-right">
                            {c.sqft_above_grade?.toLocaleString() || "--"}
                          </td>
                          <td className="px-3 py-2 text-right">
                            {c.full_baths || "--"}
                          </td>
                          <td className="px-3 py-2 text-right">
                            {c.year_built || "--"}
                          </td>
                          <td className="px-3 py-2">
                            {c.sqft_conflict ? (
                              <Badge label="Yes" variant="warning" size="sm" />
                            ) : (
                              <span className="text-gray-400">No</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {deepComp.unresolved_unknowns.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <h4 className="text-xs font-medium text-amber-700 mb-1">
                  Unresolved Unknowns
                </h4>
                <ul className="text-xs text-amber-700 space-y-0.5">
                  {deepComp.unresolved_unknowns.map((u, i) => (
                    <li key={i}>- {u}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="text-sm text-gray-500 text-center py-6 bg-gray-50 rounded-lg">
            No deep comp data. Click "Run Deep Comp" to analyze (~2 min).
          </div>
        )}
      </div>
    </div>
  );
}

// =====================================================================
// Tab 6: County Records
// =====================================================================

function CountyTab({
  data,
  loading,
  propertyId,
  onRefresh,
  refreshing,
}: {
  data: CountyData | null;
  loading: boolean;
  propertyId: string;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  if (loading) {
    return <div className="text-gray-500 text-sm">Loading county data...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">County Records</h3>
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-50"
        >
          {refreshing ? "Refreshing..." : "Refresh County"}
        </button>
      </div>

      {!data ? (
        <div className="text-gray-500 text-sm text-center py-8">
          No county data available. Click "Refresh County" to fetch records.
        </div>
      ) : (
        <>
          {/* Assessments */}
          <div>
            <h4 className="text-sm font-medium text-gray-600 mb-2">
              Tax Assessments
            </h4>
            {data.assessments.length === 0 ? (
              <p className="text-sm text-gray-500">No assessment records.</p>
            ) : (
              <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 text-gray-600 text-left">
                      <th className="px-3 py-2 font-medium">Year</th>
                      <th className="px-3 py-2 font-medium text-right">Land</th>
                      <th className="px-3 py-2 font-medium text-right">Improvement</th>
                      <th className="px-3 py-2 font-medium text-right">Total</th>
                      <th className="px-3 py-2 font-medium text-right">Annual Tax</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {data.assessments.map((a) => (
                      <tr key={a.id}>
                        <td className="px-3 py-2 font-medium">{a.tax_year}</td>
                        <td className="px-3 py-2 text-right">
                          {formatCurrency(a.land_value)}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {formatCurrency(a.improvement_value)}
                        </td>
                        <td className="px-3 py-2 text-right font-medium">
                          {formatCurrency(a.total_value)}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {a.annual_tax ? formatCurrency(a.annual_tax) : "--"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Permits */}
          <div>
            <h4 className="text-sm font-medium text-gray-600 mb-2">
              Building Permits
            </h4>
            {data.permits.length === 0 ? (
              <p className="text-sm text-gray-500">No permit records.</p>
            ) : (
              <div className="space-y-2">
                {data.permits.map((p) => (
                  <div
                    key={p.id}
                    className="bg-white border border-gray-200 rounded-lg p-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-900">
                        {p.type}
                        {p.permit_number && (
                          <span className="text-gray-400 ml-2">
                            #{p.permit_number}
                          </span>
                        )}
                      </span>
                      <div className="flex gap-2 items-center">
                        {p.status && (
                          <Badge
                            label={p.status}
                            variant={
                              p.status === "final"
                                ? "success"
                                : p.status === "issued"
                                  ? "info"
                                  : "muted"
                            }
                          />
                        )}
                        <span className="text-xs text-gray-500">
                          {formatDate(p.issue_date)}
                        </span>
                      </div>
                    </div>
                    {p.description && (
                      <p className="text-xs text-gray-600 mt-1">
                        {p.description}
                      </p>
                    )}
                    {p.estimated_cost && (
                      <p className="text-xs text-gray-500 mt-1">
                        Est. cost: {formatCurrency(p.estimated_cost)}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Deeds */}
          <div>
            <h4 className="text-sm font-medium text-gray-600 mb-2">
              Deed / Ownership History
            </h4>
            {data.deeds.length === 0 ? (
              <p className="text-sm text-gray-500">No deed records.</p>
            ) : (
              <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 text-gray-600 text-left">
                      <th className="px-3 py-2 font-medium">Date</th>
                      <th className="px-3 py-2 font-medium">Type</th>
                      <th className="px-3 py-2 font-medium">Grantor</th>
                      <th className="px-3 py-2 font-medium">Grantee</th>
                      <th className="px-3 py-2 font-medium text-right">Price</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {data.deeds.map((d) => (
                      <tr key={d.id}>
                        <td className="px-3 py-2">{formatDate(d.sale_date)}</td>
                        <td className="px-3 py-2">{d.deed_type || "--"}</td>
                        <td className="px-3 py-2 text-xs">{d.grantor || "--"}</td>
                        <td className="px-3 py-2 text-xs">{d.grantee || "--"}</td>
                        <td className="px-3 py-2 text-right font-medium">
                          {d.sale_price ? formatCurrency(d.sale_price) : "--"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// =====================================================================
// Tab 7: Listing History
// =====================================================================

function ListingHistoryTab({ propertyId, listingData }: { propertyId: string; listingData: Record<string, unknown> }) {
  const ld = listingData || {};
  const priceHistory = (ld.price_history as Array<Record<string, unknown>>) || [];
  const dom = (ld.days_on_zillow || ld.dom) as number | undefined;
  const cdom = (ld.cdom) as number | undefined;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="DOM" value={dom !== undefined ? String(dom) : "--"} />
        <MetricCard label="CDOM" value={cdom !== undefined ? String(cdom) : "--"} />
        <MetricCard
          label="Original List"
          value={
            ld.original_ask
              ? formatCurrency(Number(ld.original_ask))
              : "--"
          }
        />
        <MetricCard
          label="Total Reduction"
          value={
            ld.total_reduction
              ? formatCurrency(Number(ld.total_reduction))
              : "--"
          }
        />
      </div>

      {priceHistory.length > 0 ? (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Price History
          </h3>
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-gray-600 text-left">
                  <th className="px-3 py-2 font-medium">Date</th>
                  <th className="px-3 py-2 font-medium">Event</th>
                  <th className="px-3 py-2 font-medium text-right">Price</th>
                  <th className="px-3 py-2 font-medium text-right">Change</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {priceHistory.map((event, i) => (
                  <tr key={i}>
                    <td className="px-3 py-2">
                      {(event.date as string) || "--"}
                    </td>
                    <td className="px-3 py-2">
                      <Badge
                        label={
                          ((event.event_type || event.event) as string) || "unknown"
                        }
                        variant={
                          ((event.event_type || event.event) as string) === "price_change"
                            ? "warning"
                            : "muted"
                        }
                        size="sm"
                      />
                    </td>
                    <td className="px-3 py-2 text-right font-medium">
                      {event.price
                        ? formatCurrency(Number(event.price))
                        : "--"}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {event.change_amount
                        ? formatCurrency(Number(event.change_amount))
                        : "--"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="text-sm text-gray-500 text-center py-8 bg-gray-50 rounded-lg">
          No listing history data available. Run the pipeline to extract price
          history from the listing page.
        </div>
      )}
    </div>
  );
}

// =====================================================================
// Tab 8: Schools
// =====================================================================

function SchoolsTab({ propertyId, listingData }: { propertyId: string; listingData: Record<string, unknown> }) {
  const ld = listingData || {};

  // Get schools from listing data (Zillow assigned_schools or nearby_schools)
  const rawSchools = (ld.assigned_schools || ld.nearby_schools || []) as Array<Record<string, unknown>>;

  const schools: SchoolInfo[] = rawSchools.map((s) => ({
    name: (s.name as string) || "Unknown",
    rating: (s.rating as number) || 0,
    level: (s.level as string) || "",
    grades: (s.grades as string) || "",
    distance_mi: (s.distance_mi as number) || (s.distance as number) || 0,
    enrollment: s.enrollment as number | undefined,
    student_teacher_ratio: s.student_teacher_ratio as number | undefined,
  }));

  if (schools.length === 0) {
    return (
      <div className="text-sm text-gray-500">
        No school data available. Run the pipeline to fetch school information.
      </div>
    );
  }

  return <SchoolPanel schools={schools} />;
}

// =====================================================================
// Tab 9: AI Analysis
// =====================================================================

function AIAnalysisTab({
  packet,
  propertyId,
}: {
  packet: DecisionPacket | null;
  propertyId: string;
}) {
  const [runs, setRuns] = useState<PipelineRunDetail[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getPipelineRuns(propertyId, 5)
      .then(setRuns)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [propertyId]);

  if (loading) {
    return <div className="text-sm text-gray-500">Loading...</div>;
  }

  // Extract AI analysis results from pipeline tasks
  let aiPass1: Record<string, unknown> | null = null;
  let aiPass2: Record<string, unknown> | null = null;

  for (const run of runs) {
    for (const task of run.tasks || []) {
      if (task.task_name === "ai_pass_1" && task.result_summary) {
        aiPass1 = task.result_summary;
      }
      if (task.task_name === "ai_pass_2" && task.result_summary) {
        aiPass2 = task.result_summary;
      }
    }
    if (aiPass1 || aiPass2) break;
  }

  return (
    <div className="space-y-6">
      {/* AI Pass 1 */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          AI Pass 1: Component Extraction
        </h3>
        {aiPass1 ? (
          <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
            {Array.isArray(aiPass1.components) && (
              <div>
                <h4 className="text-xs text-gray-500 mb-1">
                  Extracted Components
                </h4>
                <div className="flex flex-wrap gap-1">
                  {(aiPass1.components as string[]).map((c, i) => (
                    <Badge key={i} label={String(c)} variant="info" size="sm" />
                  ))}
                </div>
              </div>
            )}
            {Array.isArray(aiPass1.red_flags) && (
              <div>
                <h4 className="text-xs text-gray-500 mb-1">Red Flags</h4>
                <ul className="text-sm text-red-700 space-y-0.5">
                  {(aiPass1.red_flags as string[]).map((f, i) => (
                    <li key={i}>! {String(f)}</li>
                  ))}
                </ul>
              </div>
            )}
            {Array.isArray(aiPass1.upgrades) && (
              <div>
                <h4 className="text-xs text-gray-500 mb-1">
                  Detected Upgrades
                </h4>
                <ul className="text-sm text-green-700 space-y-0.5">
                  {(aiPass1.upgrades as string[]).map((u, i) => (
                    <li key={i}>+ {String(u)}</li>
                  ))}
                </ul>
              </div>
            )}
            {/* Raw data fallback */}
            {!Array.isArray(aiPass1.components) &&
              !Array.isArray(aiPass1.red_flags) &&
              !Array.isArray(aiPass1.upgrades) && (
                <pre className="text-xs text-gray-600 whitespace-pre-wrap">
                  {JSON.stringify(aiPass1, null, 2)}
                </pre>
              )}
          </div>
        ) : (
          <div className="text-sm text-gray-500 bg-gray-50 rounded-lg p-4 text-center">
            No AI Pass 1 data. Run the full pipeline.
          </div>
        )}
      </div>

      {/* AI Pass 2 */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          AI Pass 2: Interpretation
        </h3>
        {aiPass2 ? (
          <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
            {Array.isArray(aiPass2.pros) && (
              <div>
                <h4 className="text-xs text-gray-500 mb-1">Pros</h4>
                <ul className="text-sm text-green-700 space-y-0.5">
                  {(aiPass2.pros as string[]).map((p, i) => (
                    <li key={i}>+ {String(p)}</li>
                  ))}
                </ul>
              </div>
            )}
            {Array.isArray(aiPass2.cons) && (
              <div>
                <h4 className="text-xs text-gray-500 mb-1">Cons</h4>
                <ul className="text-sm text-red-700 space-y-0.5">
                  {(aiPass2.cons as string[]).map((c, i) => (
                    <li key={i}>- {String(c)}</li>
                  ))}
                </ul>
              </div>
            )}
            {Array.isArray(aiPass2.questions_for_agent) && (
              <div>
                <h4 className="text-xs text-gray-500 mb-1">
                  Questions for Agent
                </h4>
                <ul className="text-sm text-gray-700 space-y-0.5">
                  {(aiPass2.questions_for_agent as string[]).map((q, i) => (
                    <li key={i}>? {String(q)}</li>
                  ))}
                </ul>
              </div>
            )}
            {typeof aiPass2.interpretation === "string" && (
              <div>
                <h4 className="text-xs text-gray-500 mb-1">
                  Interpretation
                </h4>
                <p className="text-sm text-gray-700">
                  {aiPass2.interpretation}
                </p>
              </div>
            )}
            {!Array.isArray(aiPass2.pros) &&
              !Array.isArray(aiPass2.cons) &&
              !Array.isArray(aiPass2.questions_for_agent) &&
              typeof aiPass2.interpretation !== "string" && (
                <pre className="text-xs text-gray-600 whitespace-pre-wrap">
                  {JSON.stringify(aiPass2, null, 2)}
                </pre>
              )}
          </div>
        ) : (
          <div className="text-sm text-gray-500 bg-gray-50 rounded-lg p-4 text-center">
            No AI Pass 2 data. Run the full pipeline.
          </div>
        )}
      </div>

      {/* Listing vs County Validation */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Listing vs County Validation
        </h3>
        {packet ? (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-xs text-gray-500 mb-1">
                  Hidden Costs
                </div>
                {packet.hidden_cost.capex_items &&
                packet.hidden_cost.capex_items.length > 0 ? (
                  <ul className="space-y-0.5">
                    {packet.hidden_cost.capex_items.map((item, i) => (
                      <li key={i} className="text-gray-700 text-xs">
                        {String(item.name || item.type || "Item")}
                        {item.cost ? `: ${formatCurrency(Number(item.cost))}` : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-gray-400 text-xs">None identified</span>
                )}
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-1">
                  Permit Concerns
                </div>
                {packet.hidden_cost.permit_concerns &&
                packet.hidden_cost.permit_concerns.length > 0 ? (
                  <ul className="space-y-0.5">
                    {packet.hidden_cost.permit_concerns.map((c, i) => (
                      <li key={i} className="text-amber-700 text-xs">
                        {c}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-gray-400 text-xs">None</span>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-gray-500 bg-gray-50 rounded-lg p-4 text-center">
            No validation data. Run the full pipeline to generate.
          </div>
        )}
      </div>
    </div>
  );
}

// =====================================================================
// Tab 10: Notes
// =====================================================================

function NotesTab({
  notes,
  loading,
  newContent,
  newType,
  onContentChange,
  onTypeChange,
  onAdd,
  onDelete,
}: {
  notes: PropertyNote[];
  loading: boolean;
  newContent: string;
  newType: string;
  onContentChange: (v: string) => void;
  onTypeChange: (v: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
}) {
  const noteTypes = ["general", "showing", "concern", "positive", "question"];

  return (
    <div className="space-y-4">
      {/* Add note form */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Add Note</h3>
        <textarea
          value={newContent}
          onChange={(e) => onContentChange(e.target.value)}
          placeholder="Write a note about this property..."
          rows={3}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 mb-2"
        />
        <div className="flex items-center justify-between">
          <select
            value={newType}
            onChange={(e) => onTypeChange(e.target.value)}
            className="text-sm border border-gray-300 rounded px-2 py-1"
          >
            {noteTypes.map((t) => (
              <option key={t} value={t}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </option>
            ))}
          </select>
          <button
            onClick={onAdd}
            disabled={!newContent.trim()}
            className="px-4 py-1.5 text-sm text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            Add Note
          </button>
        </div>
      </div>

      {/* Notes list */}
      {loading ? (
        <div className="text-gray-500 text-sm">Loading notes...</div>
      ) : notes.length === 0 ? (
        <div className="text-gray-500 text-sm text-center py-8">
          No notes yet.
        </div>
      ) : (
        <div className="space-y-2">
          {notes.map((note) => (
            <div
              key={note.id}
              className="bg-white border border-gray-200 rounded-lg p-4"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <p className="text-sm text-gray-900 whitespace-pre-wrap">
                    {note.content}
                  </p>
                  <div className="flex items-center gap-2 mt-2">
                    <Badge
                      label={note.note_type}
                      variant={
                        note.note_type === "concern"
                          ? "warning"
                          : note.note_type === "positive"
                            ? "success"
                            : note.note_type === "showing"
                              ? "info"
                              : note.note_type === "question"
                                ? "warning"
                                : "muted"
                      }
                    />
                    <span className="text-xs text-gray-400">
                      {formatDate(note.created_at)}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => onDelete(note.id)}
                  className="text-gray-400 hover:text-red-500 ml-2 text-sm"
                  title="Delete note"
                >
                  x
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
