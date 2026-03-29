"use client";

/**
 * Property detail page with tabbed interface.
 *
 * Tabs: Summary | Financial | County | Notes
 * (Condition, HOA, Risks, Documents tabs are placeholders for future phases.)
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import Badge, { stageBadgeVariant } from "@/components/common/Badge";
import FinancialPanel from "@/components/analysis/FinancialPanel";
import type {
  Property,
  WatchlistEntry,
  WatchlistStage,
  CountyData,
  PropertyNote,
} from "@/types/property";

const TABS = [
  "Summary",
  "Financial",
  "Condition",
  "County",
  "HOA",
  "Risks",
  "Documents",
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

export default function PropertyDetailPage() {
  const params = useParams();
  const propertyId = params.id as string;

  const [property, setProperty] = useState<Property | null>(null);
  const [watchEntry, setWatchEntry] = useState<WatchlistEntry | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("Summary");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // County data
  const [countyData, setCountyData] = useState<CountyData | null>(null);
  const [countyLoading, setCountyLoading] = useState(false);

  // Notes
  const [notes, setNotes] = useState<PropertyNote[]>([]);
  const [newNoteContent, setNewNoteContent] = useState("");
  const [newNoteType, setNewNoteType] = useState("general");
  const [notesLoading, setNotesLoading] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [prop, watchlist] = await Promise.all([
          api.getProperty(propertyId),
          api.listWatchlist(),
        ]);
        setProperty(prop);
        const entry = watchlist.find((w) => w.property_id === propertyId);
        setWatchEntry(entry || null);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load property"
        );
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [propertyId]);

  // Load county data when tab is selected
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

  // Load notes when tab is selected
  useEffect(() => {
    if (activeTab === "Notes" && !notesLoading) {
      loadNotes();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, propertyId]);

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

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {currentAddress?.normalized_address || "No address"}
            </h1>
            <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
              {currentAddress?.city && <span>{currentAddress.city}</span>}
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

      {/* Tabs */}
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

      {/* Tab content */}
      <div>
        {activeTab === "Summary" && (
          <SummaryTab property={property} watchEntry={watchEntry} />
        )}
        {activeTab === "Financial" && (
          <FinancialPanel propertyId={propertyId} />
        )}
        {activeTab === "Condition" && <PlaceholderTab name="Condition" />}
        {activeTab === "County" && (
          <CountyTab data={countyData} loading={countyLoading} />
        )}
        {activeTab === "HOA" && <PlaceholderTab name="HOA" />}
        {activeTab === "Risks" && <PlaceholderTab name="Risks" />}
        {activeTab === "Documents" && <PlaceholderTab name="Documents" />}
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

// --- Sub-components ---

function SummaryTab({
  property,
  watchEntry,
}: {
  property: Property;
  watchEntry: WatchlistEntry | null;
}) {
  const currentAddress = property.addresses.find(
    (a) => a.is_current && a.address_type === "situs"
  );

  return (
    <div className="space-y-6">
      {/* Key info grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <InfoCard label="Property Type" value={property.property_type.replace(/_/g, " ")} />
        <InfoCard
          label="County"
          value={currentAddress?.county || "--"}
        />
        <InfoCard
          label="ZIP Code"
          value={currentAddress?.zip_code || "--"}
        />
        <InfoCard
          label="Watchlist Stage"
          value={watchEntry?.stage || "Not on watchlist"}
        />
      </div>

      {/* Address details */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">
          Address History
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
      </div>

      {/* Parcel identifiers */}
      {property.parcel_identifiers.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Parcel Identifiers
          </h3>
          <div className="space-y-2">
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
        </div>
      )}
    </div>
  );
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-sm font-semibold text-gray-900 capitalize">
        {value}
      </div>
    </div>
  );
}

function CountyTab({
  data,
  loading,
}: {
  data: CountyData | null;
  loading: boolean;
}) {
  if (loading) {
    return <div className="text-gray-500 text-sm">Loading county data...</div>;
  }

  if (!data) {
    return (
      <div className="text-gray-500 text-sm">
        No county data available. Try refreshing county records.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Assessments */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Tax Assessments
        </h3>
        {data.assessments.length === 0 ? (
          <p className="text-sm text-gray-500">No assessment records.</p>
        ) : (
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-gray-600 text-left">
                  <th className="px-3 py-2 font-medium">Year</th>
                  <th className="px-3 py-2 font-medium text-right">Land</th>
                  <th className="px-3 py-2 font-medium text-right">
                    Improvement
                  </th>
                  <th className="px-3 py-2 font-medium text-right">Total</th>
                  <th className="px-3 py-2 font-medium text-right">
                    Annual Tax
                  </th>
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
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Building Permits
        </h3>
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
                  <p className="text-xs text-gray-600 mt-1">{p.description}</p>
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
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Deed / Ownership History
        </h3>
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
    </div>
  );
}

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
  const noteTypes = ["general", "showing", "concern", "positive"];

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

function PlaceholderTab({ name }: { name: string }) {
  return (
    <div className="text-center py-12 text-gray-500">
      <p className="text-lg mb-1">{name}</p>
      <p className="text-sm">This tab will be available in a future update.</p>
    </div>
  );
}
