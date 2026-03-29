"use client";

/**
 * Condition Panel — shows component cards in a grid,
 * each with type, age, source, confidence, and replacement cost.
 * Includes a capex forecast bar chart (text-based).
 */

import Badge from "@/components/common/Badge";
import type { ComponentInfo, ConditionResult } from "@/types/property";

interface ConditionPanelProps {
  conditionResult?: ConditionResult | null;
  components?: ComponentInfo[];
}

function formatCurrency(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

const COMPONENT_ICONS: Record<string, string> = {
  roof: "^",
  hvac: "~",
  water_heater: "W",
  furnace: "F",
  ac: "A",
  electrical: "E",
  plumbing: "P",
  windows: "#",
  siding: "|",
  deck: "D",
  appliances: "K",
  garage_door: "G",
  driveway: "=",
  septic: "S",
};

function getIcon(type: string): string {
  return COMPONENT_ICONS[type.toLowerCase()] || type.charAt(0).toUpperCase();
}

function confidenceVariant(
  confidence?: string
): "success" | "warning" | "muted" {
  if (!confidence) return "muted";
  switch (confidence.toLowerCase()) {
    case "high":
      return "success";
    case "medium":
      return "warning";
    default:
      return "muted";
  }
}

function sourceVariant(source?: string): "info" | "warning" | "muted" {
  if (!source) return "muted";
  switch (source.toLowerCase()) {
    case "county":
      return "info";
    case "listing":
      return "warning";
    case "ai":
      return "muted";
    default:
      return "muted";
  }
}

function ComponentCard({ comp }: { comp: ComponentInfo }) {
  const currentYear = new Date().getFullYear();
  const age = comp.age ?? (comp.install_year ? currentYear - comp.install_year : undefined);

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gray-100 rounded-lg flex items-center justify-center text-sm font-bold text-gray-500">
            {getIcon(comp.type)}
          </div>
          <div>
            <div className="text-sm font-medium text-gray-900 capitalize">
              {comp.type.replace(/_/g, " ")}
            </div>
            {comp.install_year && (
              <div className="text-xs text-gray-500">
                Installed {comp.install_year}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-1.5 mt-3">
        {age !== undefined && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Age</span>
            <span
              className={`font-medium ${age > 15 ? "text-red-600" : age > 10 ? "text-amber-600" : "text-green-600"}`}
            >
              {age} years
            </span>
          </div>
        )}
        {comp.remaining_life !== undefined && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Est. remaining</span>
            <span
              className={`font-medium ${comp.remaining_life < 3 ? "text-red-600" : comp.remaining_life < 7 ? "text-amber-600" : "text-green-600"}`}
            >
              {comp.remaining_life} years
            </span>
          </div>
        )}
        {comp.replacement_cost !== undefined && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Replacement</span>
            <span className="font-medium text-gray-900">
              {formatCurrency(comp.replacement_cost)}
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-1.5 mt-3">
        {comp.source && (
          <Badge
            label={comp.source}
            variant={sourceVariant(comp.source)}
            size="sm"
          />
        )}
        {comp.confidence && (
          <Badge
            label={comp.confidence}
            variant={confidenceVariant(comp.confidence)}
            size="sm"
          />
        )}
      </div>
    </div>
  );
}

function CapexForecast({
  forecast,
}: {
  forecast: Record<number, number>;
}) {
  const entries = Object.entries(forecast)
    .map(([year, cost]) => ({ year: parseInt(year), cost }))
    .sort((a, b) => a.year - b.year);

  if (entries.length === 0) {
    return null;
  }

  const maxCost = Math.max(...entries.map((e) => e.cost));

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <h4 className="text-sm font-semibold text-gray-700 mb-3">
        Capex Forecast
      </h4>
      <div className="space-y-2">
        {entries.map(({ year, cost }) => (
          <div key={year} className="flex items-center gap-3">
            <span className="text-xs font-medium text-gray-500 w-10">
              {year}
            </span>
            <div className="flex-1 h-5 bg-gray-100 rounded relative">
              <div
                className={`h-full rounded ${cost > 5000 ? "bg-red-400" : cost > 2000 ? "bg-amber-400" : "bg-green-400"}`}
                style={{
                  width: `${maxCost > 0 ? (cost / maxCost) * 100 : 0}%`,
                  minWidth: cost > 0 ? "2px" : "0",
                }}
              />
            </div>
            <span className="text-xs font-medium text-gray-700 w-20 text-right">
              {formatCurrency(cost)}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-2 pt-2 border-t border-gray-100 flex justify-between text-xs">
        <span className="text-gray-500">Total projected</span>
        <span className="font-medium text-gray-900">
          {formatCurrency(entries.reduce((sum, e) => sum + e.cost, 0))}
        </span>
      </div>
    </div>
  );
}

export default function ConditionPanel({
  conditionResult,
  components,
}: ConditionPanelProps) {
  if (!conditionResult && (!components || components.length === 0)) {
    return (
      <div className="text-sm text-gray-500 text-center py-8">
        No condition data available. Run the pipeline to analyze property
        components.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {conditionResult && (
        <div className="flex items-center gap-4 bg-white border border-gray-200 rounded-lg p-4">
          <div>
            <div className="text-xs text-gray-500">Condition Score</div>
            <div
              className={`text-2xl font-bold ${conditionResult.condition_score >= 70 ? "text-green-600" : conditionResult.condition_score >= 40 ? "text-amber-600" : "text-red-600"}`}
            >
              {conditionResult.condition_score.toFixed(0)}/100
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Components Analyzed</div>
            <div className="text-2xl font-bold text-gray-900">
              {conditionResult.components_analyzed}
            </div>
          </div>
        </div>
      )}

      {components && components.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Components
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {components.map((comp, i) => (
              <ComponentCard key={`${comp.type}-${i}`} comp={comp} />
            ))}
          </div>
        </div>
      )}

      {conditionResult?.capex_forecast &&
        Object.keys(conditionResult.capex_forecast).length > 0 && (
          <CapexForecast forecast={conditionResult.capex_forecast} />
        )}
    </div>
  );
}
