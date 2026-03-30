"use client";

/**
 * School Panel — 3 cards (elementary, middle, high)
 * Each shows name, rating /10, distance, and detailed data if available.
 */

import Badge from "@/components/common/Badge";
import type { SchoolInfo } from "@/types/property";

interface SchoolPanelProps {
  schools: SchoolInfo[];
}

function ratingColor(rating?: number): string {
  if (!rating) return "text-gray-400";
  if (rating >= 8) return "text-green-600";
  if (rating >= 6) return "text-amber-600";
  if (rating >= 4) return "text-orange-600";
  return "text-red-600";
}

function ratingBg(rating?: number): string {
  if (!rating) return "bg-gray-100";
  if (rating >= 8) return "bg-green-50 border-green-200";
  if (rating >= 6) return "bg-amber-50 border-amber-200";
  if (rating >= 4) return "bg-orange-50 border-orange-200";
  return "bg-red-50 border-red-200";
}

function levelIcon(level: string): string {
  switch (level.toLowerCase()) {
    case "elementary":
      return "E";
    case "middle":
      return "M";
    case "high":
      return "H";
    default:
      return "S";
  }
}

function SchoolCard({ school }: { school: SchoolInfo }) {
  return (
    <div className={`border rounded-lg p-4 ${ratingBg(school.rating)}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-white border border-gray-200 rounded-lg flex items-center justify-center text-sm font-bold text-gray-500">
            {levelIcon(school.level)}
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wide">
              {school.level}
            </div>
            <div className="text-sm font-medium text-gray-900">
              {school.name}
            </div>
          </div>
        </div>
        {school.assigned && (
          <Badge label="Assigned" variant="info" size="sm" />
        )}
      </div>

      <div className="flex items-end justify-between">
        <div>
          {school.distance_mi !== undefined && (
            <div className="text-xs text-gray-500">
              {school.distance_mi.toFixed(1)} mi away
            </div>
          )}
        </div>
        <div className="text-right">
          {school.rating !== undefined ? (
            <div>
              <span
                className={`text-2xl font-bold ${ratingColor(school.rating)}`}
              >
                {school.rating}
              </span>
              <span className="text-sm text-gray-400">/10</span>
            </div>
          ) : (
            <span className="text-sm text-gray-400">No rating</span>
          )}
        </div>
      </div>

      {(school.enrollment ||
        school.student_teacher_ratio ||
        school.test_scores) && (
        <div className="mt-3 pt-3 border-t border-gray-200/50 space-y-1.5">
          {school.enrollment && (
            <div className="flex justify-between text-xs">
              <span className="text-gray-500">Enrollment</span>
              <span className="font-medium text-gray-700">
                {school.enrollment.toLocaleString()}
              </span>
            </div>
          )}
          {school.student_teacher_ratio && (
            <div className="flex justify-between text-xs">
              <span className="text-gray-500">Student:Teacher</span>
              <span className="font-medium text-gray-700">
                {school.student_teacher_ratio}:1
              </span>
            </div>
          )}
          {school.test_scores &&
            Object.entries(school.test_scores).map(([key, val]) => (
              <div key={key} className="flex justify-between text-xs">
                <span className="text-gray-500 capitalize">
                  {key.replace(/_/g, " ")}
                </span>
                <span className="font-medium text-gray-700">
                  {String(val)}
                </span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

export default function SchoolPanel({ schools }: SchoolPanelProps) {
  if (!schools || schools.length === 0) {
    return (
      <div className="text-sm text-gray-500 text-center py-8">
        No school data available. Run the pipeline to look up assigned schools.
      </div>
    );
  }

  // Group by level, prioritizing assigned schools
  const levels = ["elementary", "middle", "high"];
  const grouped: Record<string, SchoolInfo[]> = {};
  for (const level of levels) {
    grouped[level] = schools.filter(
      (s) => s.level.toLowerCase() === level
    );
  }
  const other = schools.filter(
    (s) => !levels.includes(s.level.toLowerCase())
  );

  const totalRating = schools
    .filter((s) => s.rating !== undefined)
    .reduce((sum, s) => sum + (s.rating || 0), 0);
  const ratedCount = schools.filter((s) => s.rating !== undefined).length;
  const avgRating = ratedCount > 0 ? totalRating / ratedCount : undefined;

  return (
    <div className="space-y-6">
      {avgRating !== undefined && (
        <div className="bg-white border border-gray-200 rounded-lg p-4 flex items-center gap-4">
          <div>
            <div className="text-xs text-gray-500">Average School Rating</div>
            <div className={`text-2xl font-bold ${ratingColor(avgRating)}`}>
              {avgRating.toFixed(1)}/10
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Schools Rated</div>
            <div className="text-2xl font-bold text-gray-900">
              {ratedCount}
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {levels.map((level) => {
          const levelSchools = grouped[level];
          if (levelSchools.length === 0) {
            return (
              <div
                key={level}
                className="border border-gray-200 rounded-lg p-4 bg-gray-50"
              >
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                  {level}
                </div>
                <div className="text-sm text-gray-400">No data</div>
              </div>
            );
          }
          return levelSchools.map((school, i) => (
            <SchoolCard key={`${level}-${i}`} school={school} />
          ));
        })}
      </div>

      {other.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 mb-2">
            Other Schools
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {other.map((school, i) => (
              <SchoolCard key={`other-${i}`} school={school} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
