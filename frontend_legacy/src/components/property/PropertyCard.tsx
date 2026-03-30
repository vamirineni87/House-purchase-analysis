"use client";

/**
 * Card component for displaying a property summary.
 * Shows address, county badge, property type, and date added.
 */

import Link from "next/link";
import Badge from "@/components/common/Badge";
import type { PropertySummary } from "@/types/property";

interface PropertyCardProps {
  property: PropertySummary;
}

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

function countyBadgeVariant(county?: string): "info" | "warning" | "default" {
  if (!county) return "default";
  const lower = county.toLowerCase();
  if (lower === "fairfax") return "info";
  if (lower === "loudoun") return "warning";
  return "default";
}

export default function PropertyCard({ property }: PropertyCardProps) {
  return (
    <Link href={`/properties/${property.id}`}>
      <div className="bg-white border border-gray-200 rounded-lg p-4 hover:border-blue-300 hover:shadow-sm transition-all cursor-pointer">
        <div className="flex items-start justify-between mb-2">
          <h3 className="font-medium text-gray-900 text-sm leading-tight">
            {property.address || "No address"}
          </h3>
          {property.county && (
            <Badge
              label={property.county.charAt(0).toUpperCase() + property.county.slice(1)}
              variant={countyBadgeVariant(property.county)}
              size="sm"
            />
          )}
        </div>
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>{formatPropertyType(property.property_type)}</span>
          <span>{formatDate(property.created_at)}</span>
        </div>
      </div>
    </Link>
  );
}
