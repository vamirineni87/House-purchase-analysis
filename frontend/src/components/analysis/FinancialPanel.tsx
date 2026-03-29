"use client";

/**
 * Financial analysis display panel.
 *
 * Shows scenario comparison table, monthly payment breakdown,
 * and cash-at-closing cards.
 */

import { useState } from "react";
import { api } from "@/lib/api";
import type {
  FinancialAnalysisRequest,
  FinancialAnalysisResult,
  MonthlyPaymentBreakdown,
} from "@/types/property";

interface FinancialPanelProps {
  propertyId: string;
}

function formatCurrency(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

function formatPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

export default function FinancialPanel({ propertyId }: FinancialPanelProps) {
  const [listPrice, setListPrice] = useState("");
  const [hoaMonthly, setHoaMonthly] = useState("");
  const [result, setResult] = useState<FinancialAnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runAnalysis() {
    const price = parseFloat(listPrice);
    if (isNaN(price) || price <= 0) {
      setError("Enter a valid list price.");
      return;
    }

    setError(null);
    setLoading(true);
    try {
      const req: FinancialAnalysisRequest = {
        list_price: price,
        hoa_monthly: parseFloat(hoaMonthly) || 0,
        down_payment_pcts: [0.1, 0.2],
        term_years: [15, 30],
      };
      const data = await api.runFinancialAnalysis(propertyId, req);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Input form */}
      <div className="bg-gray-50 rounded-lg p-4 flex flex-wrap gap-4 items-end">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            List Price
          </label>
          <input
            type="number"
            value={listPrice}
            onChange={(e) => setListPrice(e.target.value)}
            placeholder="650000"
            className="border border-gray-300 rounded px-3 py-2 text-sm w-40"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            HOA/month
          </label>
          <input
            type="number"
            value={hoaMonthly}
            onChange={(e) => setHoaMonthly(e.target.value)}
            placeholder="0"
            className="border border-gray-300 rounded px-3 py-2 text-sm w-28"
          />
        </div>
        <button
          onClick={runAnalysis}
          disabled={loading}
          className="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Running..." : "Run Analysis"}
        </button>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">
          {error}
        </div>
      )}

      {result && (
        <>
          {/* Scenario comparison table */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-2">
              Loan Scenarios
            </h3>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 text-gray-600 text-left">
                    <th className="px-3 py-2 font-medium">Scenario</th>
                    <th className="px-3 py-2 font-medium text-right">Down Payment</th>
                    <th className="px-3 py-2 font-medium text-right">Loan Amount</th>
                    <th className="px-3 py-2 font-medium text-right">Rate</th>
                    <th className="px-3 py-2 font-medium text-right">Term</th>
                    <th className="px-3 py-2 font-medium text-right">Monthly Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {result.scenarios.map((s) => {
                    const breakdown = result.payment_breakdowns[s.name];
                    return (
                      <tr key={s.name} className="hover:bg-gray-50">
                        <td className="px-3 py-2 font-medium text-gray-900">
                          {s.name}
                        </td>
                        <td className="px-3 py-2 text-right text-gray-700">
                          {formatCurrency(s.down_payment)}{" "}
                          <span className="text-gray-400">
                            ({formatPct(s.down_payment_pct)})
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right text-gray-700">
                          {formatCurrency(s.loan_amount)}
                        </td>
                        <td className="px-3 py-2 text-right text-gray-700">
                          {s.interest_rate.toFixed(2)}%
                        </td>
                        <td className="px-3 py-2 text-right text-gray-700">
                          {s.term_years}yr
                        </td>
                        <td className="px-3 py-2 text-right font-semibold text-gray-900">
                          {breakdown ? formatCurrency(breakdown.total) : "--"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Payment breakdowns */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-2">
              Monthly Payment Breakdown
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {result.scenarios.map((s) => {
                const bd = result.payment_breakdowns[s.name];
                if (!bd) return null;
                return (
                  <PaymentBreakdownCard
                    key={s.name}
                    name={s.name}
                    breakdown={bd}
                  />
                );
              })}
            </div>
          </div>

          {/* Cash at closing */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-2">
              Cash Needed at Closing
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(result.cash_needed_at_closing).map(
                ([name, amount]) => (
                  <div
                    key={name}
                    className="bg-white border border-gray-200 rounded-lg p-4 text-center"
                  >
                    <div className="text-xs text-gray-500 mb-1">{name}</div>
                    <div className="text-lg font-bold text-gray-900">
                      {formatCurrency(amount)}
                    </div>
                  </div>
                )
              )}
            </div>
          </div>

          {/* Closing costs summary */}
          {result.closing_costs && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">
                Estimated Closing Costs
              </h3>
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="text-gray-600">Loan origination</div>
                  <div className="text-right">{formatCurrency(result.closing_costs.loan_origination)}</div>
                  <div className="text-gray-600">Appraisal fee</div>
                  <div className="text-right">{formatCurrency(result.closing_costs.appraisal_fee)}</div>
                  <div className="text-gray-600">Title insurance</div>
                  <div className="text-right">{formatCurrency(result.closing_costs.title_insurance)}</div>
                  <div className="text-gray-600">Escrow fees</div>
                  <div className="text-right">{formatCurrency(result.closing_costs.escrow_fees)}</div>
                  <div className="text-gray-600">Recording fees</div>
                  <div className="text-right">{formatCurrency(result.closing_costs.recording_fees)}</div>
                  <div className="text-gray-600">Prepaid taxes</div>
                  <div className="text-right">{formatCurrency(result.closing_costs.prepaid_taxes)}</div>
                  <div className="text-gray-600">Prepaid insurance</div>
                  <div className="text-right">{formatCurrency(result.closing_costs.prepaid_insurance)}</div>
                  <div className="text-gray-600">Inspection fees</div>
                  <div className="text-right">{formatCurrency(result.closing_costs.inspection_fees)}</div>
                  <div className="text-gray-600">Other</div>
                  <div className="text-right">{formatCurrency(result.closing_costs.other)}</div>
                  <div className="font-semibold text-gray-900 border-t pt-2">Total</div>
                  <div className="font-semibold text-right border-t pt-2">
                    {formatCurrency(result.closing_costs.total)}
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function PaymentBreakdownCard({
  name,
  breakdown,
}: {
  name: string;
  breakdown: MonthlyPaymentBreakdown;
}) {
  const items = [
    { label: "Principal", value: breakdown.principal, color: "bg-blue-500" },
    { label: "Interest", value: breakdown.interest, color: "bg-indigo-400" },
    { label: "Property Tax", value: breakdown.property_tax, color: "bg-amber-400" },
    { label: "Insurance", value: breakdown.homeowners_insurance, color: "bg-green-400" },
    { label: "PMI", value: breakdown.pmi, color: "bg-red-400" },
    { label: "HOA", value: breakdown.hoa, color: "bg-purple-400" },
  ].filter((item) => item.value > 0);

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex justify-between items-center mb-3">
        <h4 className="text-sm font-medium text-gray-900">{name}</h4>
        <span className="text-lg font-bold text-gray-900">
          {formatCurrency(breakdown.total)}/mo
        </span>
      </div>

      {/* Stacked bar */}
      <div className="flex h-3 rounded-full overflow-hidden mb-3">
        {items.map((item) => (
          <div
            key={item.label}
            className={`${item.color}`}
            style={{ width: `${(item.value / breakdown.total) * 100}%` }}
            title={`${item.label}: ${formatCurrency(item.value)}`}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="grid grid-cols-2 gap-1 text-xs">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${item.color}`} />
            <span className="text-gray-600">{item.label}</span>
            <span className="ml-auto text-gray-900 font-medium">
              {formatCurrency(item.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
