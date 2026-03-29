"use client";

/**
 * Add Property Modal — supports both URL ingest (paste Zillow/Redfin/Realtor URL)
 * and manual address entry. Calls ingestProperty API.
 */

import { useState } from "react";
import { api } from "@/lib/api";

interface AddPropertyModalProps {
  open: boolean;
  onClose: () => void;
  onAdded: (propertyId: string) => void;
}

type InputMode = "url" | "address";

export default function AddPropertyModal({
  open,
  onClose,
  onAdded,
}: AddPropertyModalProps) {
  const [mode, setMode] = useState<InputMode>("url");
  const [url, setUrl] = useState("");
  const [street, setStreet] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("VA");
  const [zipCode, setZipCode] = useState("");
  const [propertyType, setPropertyType] = useState("single_family");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (mode === "url") {
        if (!url.trim()) {
          setError("Paste a listing URL.");
          setLoading(false);
          return;
        }
        const result = await api.ingestProperty({ url: url.trim() });
        onAdded(result.property.id);
      } else {
        if (!street.trim() || !city.trim()) {
          setError("Street and city are required.");
          setLoading(false);
          return;
        }
        const result = await api.ingestProperty({
          address: {
            street: street.trim(),
            city: city.trim(),
            state: state.trim() || "VA",
            zip_code: zipCode.trim(),
          },
          property_type: propertyType,
        });
        onAdded(result.property.id);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to add property"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />
      <div className="relative bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Add Property
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
          >
            x
          </button>
        </div>

        {/* Mode toggle */}
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-4">
          <button
            onClick={() => setMode("url")}
            className={`flex-1 px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              mode === "url"
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            Paste URL
          </button>
          <button
            onClick={() => setMode("address")}
            className={`flex-1 px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              mode === "address"
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            Manual Address
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === "url" ? (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Listing URL
              </label>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.zillow.com/homedetails/..."
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                autoFocus
              />
              <p className="text-xs text-gray-500 mt-1">
                Supports Zillow, Redfin, and Realtor.com URLs
              </p>
            </div>
          ) : (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Street Address
                </label>
                <input
                  type="text"
                  value={street}
                  onChange={(e) => setStreet(e.target.value)}
                  placeholder="123 Main St"
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  autoFocus
                />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    City
                  </label>
                  <input
                    type="text"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    placeholder="Fairfax"
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    State
                  </label>
                  <input
                    type="text"
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    ZIP
                  </label>
                  <input
                    type="text"
                    value={zipCode}
                    onChange={(e) => setZipCode(e.target.value)}
                    placeholder="22030"
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Property Type
                </label>
                <select
                  value={propertyType}
                  onChange={(e) => setPropertyType(e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="single_family">Single Family</option>
                  <option value="townhouse">Townhouse</option>
                  <option value="condo">Condo</option>
                  <option value="multi_family">Multi Family</option>
                </select>
              </div>
            </>
          )}

          {error && (
            <div className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">
              {error}
            </div>
          )}

          {loading && (
            <div className="text-sm text-blue-600 bg-blue-50 rounded px-3 py-2">
              {mode === "url"
                ? "Scraping listing page... this may take 10-20 seconds."
                : "Creating property..."}
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {loading
                ? mode === "url"
                  ? "Ingesting..."
                  : "Adding..."
                : "Add Property"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
