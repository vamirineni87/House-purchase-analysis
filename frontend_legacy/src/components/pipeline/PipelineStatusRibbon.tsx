"use client";

/**
 * Pipeline status ribbon — shows run status, task counts, failed task names,
 * and a retry button for failed tasks.
 */

import { useState } from "react";
import Badge from "@/components/common/Badge";
import type { PipelineRunDetail } from "@/types/property";

interface PipelineStatusRibbonProps {
  latestRun?: PipelineRunDetail | null;
  onRetryFailed?: () => void;
  onRunPipeline?: () => void;
  loading?: boolean;
}

function statusVariant(
  status: string
): "success" | "critical" | "warning" | "info" | "muted" {
  switch (status) {
    case "succeeded":
      return "success";
    case "failed":
      return "critical";
    case "partial_success":
      return "warning";
    case "running":
    case "queued":
      return "info";
    case "cancelled":
      return "muted";
    default:
      return "muted";
  }
}

function statusLabel(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function PipelineStatusRibbon({
  latestRun,
  onRetryFailed,
  onRunPipeline,
  loading,
}: PipelineStatusRibbonProps) {
  if (!latestRun) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 flex items-center justify-between">
        <span className="text-sm text-gray-500">
          No pipeline has been run yet.
        </span>
        {onRunPipeline && (
          <button
            onClick={onRunPipeline}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Starting..." : "Run Full Pipeline"}
          </button>
        )}
      </div>
    );
  }

  const tasks = latestRun.tasks || [];
  const succeeded = tasks.filter((t) => t.status === "succeeded").length;
  const failed = tasks.filter((t) => t.status === "failed").length;
  const pending = tasks.filter(
    (t) => t.status === "pending" || t.status === "queued"
  ).length;
  const running = tasks.filter((t) => t.status === "running").length;
  const total = tasks.length;
  const failedNames = tasks
    .filter((t) => t.status === "failed")
    .map((t) => t.task_name.replace(/_/g, " "));

  return (
    <div className="bg-white border border-gray-200 rounded-lg px-4 py-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <Badge
            label={statusLabel(latestRun.status)}
            variant={statusVariant(latestRun.status)}
            size="md"
          />
          <span className="text-sm text-gray-600">
            {succeeded}/{total} tasks succeeded
            {failed > 0 && (
              <span className="text-red-600 ml-1">
                , {failed} failed
              </span>
            )}
            {running > 0 && (
              <span className="text-blue-600 ml-1">
                , {running} running
              </span>
            )}
            {pending > 0 && (
              <span className="text-gray-400 ml-1">
                , {pending} pending
              </span>
            )}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {failed > 0 && onRetryFailed && (
            <button
              onClick={onRetryFailed}
              disabled={loading}
              className="px-3 py-1.5 text-xs font-medium text-white bg-red-600 rounded hover:bg-red-700 disabled:opacity-50"
            >
              {loading ? "Retrying..." : "Retry Failed"}
            </button>
          )}
          {onRunPipeline && (
            <button
              onClick={onRunPipeline}
              disabled={loading}
              className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? "Starting..." : "Run Full Pipeline"}
            </button>
          )}
        </div>
      </div>

      {failedNames.length > 0 && (
        <div className="mt-2 text-xs text-red-600">
          Failed: {failedNames.join(", ")}
        </div>
      )}

      {latestRun.status === "running" && (
        <div className="mt-2">
          <div className="w-full bg-gray-100 rounded-full h-1.5">
            <div
              className="bg-blue-500 h-1.5 rounded-full transition-all animate-pulse"
              style={{
                width: `${total > 0 ? ((succeeded + failed) / total) * 100 : 0}%`,
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
