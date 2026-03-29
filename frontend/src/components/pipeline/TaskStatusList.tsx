"use client";

/**
 * Task status list — shows each pipeline task with status dots,
 * duration, error details, and rerun buttons.
 */

import { useState } from "react";
import Badge from "@/components/common/Badge";
import type { PipelineTaskRun } from "@/types/property";

interface TaskStatusListProps {
  tasks: PipelineTaskRun[];
  onRerunTask?: (taskName: string) => void;
  rerunning?: string | null;
}

function statusDot(status: string): string {
  switch (status) {
    case "succeeded":
      return "bg-green-500";
    case "failed":
      return "bg-red-500";
    case "running":
      return "bg-blue-500 animate-pulse";
    case "pending":
    case "queued":
      return "bg-gray-300";
    case "skipped":
      return "bg-gray-200";
    default:
      return "bg-gray-300";
  }
}

function formatDuration(ms?: number): string {
  if (!ms) return "--";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function formatTaskName(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function TaskStatusList({
  tasks,
  onRerunTask,
  rerunning,
}: TaskStatusListProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggleExpand(taskId: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  }

  if (tasks.length === 0) {
    return (
      <div className="text-sm text-gray-500">No tasks in this run.</div>
    );
  }

  return (
    <div className="space-y-1">
      {tasks.map((task) => (
        <div
          key={task.id}
          className="bg-white border border-gray-200 rounded-lg px-4 py-2.5"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <div
                className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${statusDot(task.status)}`}
              />
              <span className="text-sm font-medium text-gray-900 truncate">
                {formatTaskName(task.task_name)}
              </span>
              {task.retry_count > 0 && (
                <Badge
                  label={`${task.retry_count} retries`}
                  variant="warning"
                  size="sm"
                />
              )}
            </div>

            <div className="flex items-center gap-3 flex-shrink-0">
              <span className="text-xs text-gray-500">
                {formatDuration(task.duration_ms ?? undefined)}
              </span>
              <Badge
                label={task.status}
                variant={
                  task.status === "succeeded"
                    ? "success"
                    : task.status === "failed"
                      ? "critical"
                      : task.status === "running"
                        ? "info"
                        : "muted"
                }
                size="sm"
              />
              {task.status === "failed" && onRerunTask && (
                <button
                  onClick={() => onRerunTask(task.task_name)}
                  disabled={rerunning === task.task_name}
                  className="px-2 py-1 text-xs font-medium text-red-600 border border-red-200 rounded hover:bg-red-50 disabled:opacity-50"
                >
                  {rerunning === task.task_name ? "..." : "Rerun"}
                </button>
              )}
              {task.error_details && (
                <button
                  onClick={() => toggleExpand(task.id)}
                  className="text-xs text-gray-400 hover:text-gray-600"
                >
                  {expanded.has(task.id) ? "Hide" : "Details"}
                </button>
              )}
            </div>
          </div>

          {expanded.has(task.id) && task.error_details && (
            <div className="mt-2 ml-5 p-2 bg-red-50 rounded text-xs text-red-700 font-mono whitespace-pre-wrap break-all">
              {task.error_details}
            </div>
          )}

          {task.result_summary &&
            Object.keys(task.result_summary).length > 0 &&
            expanded.has(task.id) && (
              <div className="mt-2 ml-5 p-2 bg-gray-50 rounded text-xs text-gray-600 font-mono">
                {JSON.stringify(task.result_summary, null, 2)}
              </div>
            )}
        </div>
      ))}
    </div>
  );
}
