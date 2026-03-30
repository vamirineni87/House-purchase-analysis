"use client";

/**
 * Badge component for displaying stages, severity levels, and labels.
 */

interface BadgeProps {
  label: string;
  variant?: "default" | "info" | "warning" | "critical" | "success" | "muted";
  size?: "sm" | "md";
}

const variantStyles: Record<string, string> = {
  default: "bg-gray-100 text-gray-700",
  info: "bg-blue-100 text-blue-700",
  warning: "bg-amber-100 text-amber-700",
  critical: "bg-red-100 text-red-700",
  success: "bg-green-100 text-green-700",
  muted: "bg-gray-50 text-gray-500",
};

const sizeStyles: Record<string, string> = {
  sm: "text-xs px-2 py-0.5",
  md: "text-sm px-2.5 py-0.5",
};

export default function Badge({
  label,
  variant = "default",
  size = "sm",
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${variantStyles[variant] || variantStyles.default} ${sizeStyles[size]}`}
    >
      {label}
    </span>
  );
}

/**
 * Map a watchlist stage to a badge variant.
 */
export function stageBadgeVariant(
  stage: string
): BadgeProps["variant"] {
  const map: Record<string, BadgeProps["variant"]> = {
    researching: "info",
    touring: "warning",
    offer: "critical",
    contract: "success",
    closed: "success",
    rejected: "muted",
  };
  return map[stage] || "default";
}

/**
 * Map an alert severity to a badge variant.
 */
export function severityBadgeVariant(
  severity: string
): BadgeProps["variant"] {
  const map: Record<string, BadgeProps["variant"]> = {
    info: "info",
    warning: "warning",
    critical: "critical",
  };
  return map[severity] || "default";
}
