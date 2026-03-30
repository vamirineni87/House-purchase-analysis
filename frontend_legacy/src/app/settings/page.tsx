"use client";

/**
 * Settings page.
 * API key inputs (stored in localStorage).
 * Default financial assumptions display.
 */

import { useEffect, useState } from "react";

interface ApiKeyConfig {
  label: string;
  storageKey: string;
  placeholder: string;
}

const API_KEYS: ApiKeyConfig[] = [
  {
    label: "FRED API Key",
    storageKey: "pipa_fred_api_key",
    placeholder: "Your FRED API key",
  },
  {
    label: "RentCast API Key",
    storageKey: "pipa_rentcast_api_key",
    placeholder: "Your RentCast API key",
  },
  {
    label: "GreatSchools API Key",
    storageKey: "pipa_greatschools_api_key",
    placeholder: "Your GreatSchools API key",
  },
  {
    label: "WalkScore API Key",
    storageKey: "pipa_walkscore_api_key",
    placeholder: "Your WalkScore API key",
  },
  {
    label: "API Ninjas Key",
    storageKey: "pipa_api_ninjas_key",
    placeholder: "Your API Ninjas key",
  },
  {
    label: "Census API Key",
    storageKey: "pipa_census_api_key",
    placeholder: "Your Census API key",
  },
  {
    label: "NOAA Token",
    storageKey: "pipa_noaa_token",
    placeholder: "Your NOAA API token",
  },
];

const DEFAULT_ASSUMPTIONS = [
  { label: "30yr Mortgage Rate", value: "6.50%" },
  { label: "15yr Mortgage Rate", value: "5.90%" },
  { label: "Homeowners Insurance Rate", value: "0.35%" },
  { label: "PMI Rate", value: "0.50%" },
  { label: "PMI Threshold", value: "80% LTV" },
  { label: "Property Tax Rate (default)", value: "1.20%" },
  { label: "Appreciation Rate", value: "3.00%" },
  { label: "Inflation Rate", value: "2.50%" },
  { label: "Maintenance Rate", value: "1.00%" },
  { label: "Closing Cost Rate", value: "3.00%" },
  { label: "Vacancy Rate", value: "5.00%" },
  { label: "Marginal Tax Rate", value: "24.00%" },
  { label: "Filing Status", value: "Married" },
];

export default function SettingsPage() {
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const loaded: Record<string, string> = {};
    for (const cfg of API_KEYS) {
      loaded[cfg.storageKey] = localStorage.getItem(cfg.storageKey) || "";
    }
    setKeys(loaded);
  }, []);

  function handleChange(storageKey: string, value: string) {
    setKeys((prev) => ({ ...prev, [storageKey]: value }));
    setSaved(false);
  }

  function handleSave() {
    for (const cfg of API_KEYS) {
      const value = keys[cfg.storageKey]?.trim() || "";
      if (value) {
        localStorage.setItem(cfg.storageKey, value);
      } else {
        localStorage.removeItem(cfg.storageKey);
      }
    }
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      {/* API Keys */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          API Keys
        </h2>
        <p className="text-sm text-gray-500 mb-4">
          API keys are stored in your browser&apos;s localStorage. They are sent to the
          backend with requests that need them. Keys are never shared with third
          parties beyond the respective API provider.
        </p>
        <div className="space-y-3">
          {API_KEYS.map((cfg) => (
            <div key={cfg.storageKey}>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {cfg.label}
              </label>
              <input
                type="password"
                value={keys[cfg.storageKey] || ""}
                onChange={(e) => handleChange(cfg.storageKey, e.target.value)}
                placeholder={cfg.placeholder}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          ))}
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleSave}
            className="px-4 py-2 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700"
          >
            Save Keys
          </button>
          {saved && (
            <span className="text-sm text-green-600">Saved to localStorage.</span>
          )}
        </div>
      </section>

      {/* Default Assumptions */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Default Financial Assumptions
        </h2>
        <p className="text-sm text-gray-500 mb-4">
          These defaults are loaded from the server&apos;s config.yaml. To change them,
          edit the config file and restart the server.
        </p>
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-gray-600 text-left">
                <th className="px-4 py-2 font-medium">Parameter</th>
                <th className="px-4 py-2 font-medium text-right">
                  Default Value
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {DEFAULT_ASSUMPTIONS.map((item) => (
                <tr key={item.label}>
                  <td className="px-4 py-2 text-gray-700">{item.label}</td>
                  <td className="px-4 py-2 text-right font-mono text-gray-900">
                    {item.value}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
