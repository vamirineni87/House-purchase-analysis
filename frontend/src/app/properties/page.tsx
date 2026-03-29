"use client";

/**
 * Property list page.
 * Fetches from /api/v1/properties.
 * Table with columns: Address, County, Type, Added.
 * "Add Property" button opens inline form.
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PropertySummary } from "@/types/property";
import PropertyCard from "@/components/property/PropertyCard";
import AddPropertyForm from "@/components/property/AddPropertyForm";

export default function PropertiesPage() {
  const [properties, setProperties] = useState<PropertySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadProperties() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listProperties();
      setProperties(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load properties");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProperties();
  }, []);

  function formatPropertyType(type: string): string {
    return type
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }

  function formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Properties</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
        >
          {showForm ? "Close" : "+ Add Property"}
        </button>
      </div>

      {showForm && (
        <div className="mb-6">
          <AddPropertyForm
            onAdded={() => {
              setShowForm(false);
              loadProperties();
            }}
            onCancel={() => setShowForm(false)}
          />
        </div>
      )}

      {error && (
        <div className="text-sm text-red-600 bg-red-50 rounded px-3 py-2 mb-4">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-gray-500 text-sm">Loading properties...</div>
      ) : properties.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-2">No properties yet</p>
          <p className="text-sm">
            Click &quot;+ Add Property&quot; to start tracking.
          </p>
        </div>
      ) : (
        <>
          {/* Card view for narrow screens */}
          <div className="md:hidden space-y-3">
            {properties.map((p) => (
              <PropertyCard key={p.id} property={p} />
            ))}
          </div>

          {/* Table view for wider screens */}
          <div className="hidden md:block bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-gray-600 text-left">
                  <th className="px-4 py-3 font-medium">Address</th>
                  <th className="px-4 py-3 font-medium">County</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Added</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {properties.map((p) => (
                  <tr
                    key={p.id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() =>
                      (window.location.href = `/properties/${p.id}`)
                    }
                  >
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {p.address || "No address"}
                    </td>
                    <td className="px-4 py-3 text-gray-700 capitalize">
                      {p.county || "--"}
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      {formatPropertyType(p.property_type)}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {formatDate(p.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
