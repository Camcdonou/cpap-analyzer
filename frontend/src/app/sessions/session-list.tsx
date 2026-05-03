"use client";

import Link from "next/link";
import type { SessionSummary } from "@/lib/api";

function ahiColor(ahi: number): string {
  if (ahi < 5) return "var(--color-success)";
  if (ahi < 15) return "var(--color-warning)";
  if (ahi < 30) return "var(--color-danger)";
  return "var(--color-danger)";
}

function ahiLabel(ahi: number): string {
  if (ahi < 5) return "Normal";
  if (ahi < 15) return "Mild";
  if (ahi < 30) return "Moderate";
  return "Severe";
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function SessionList({ sessions }: { sessions: SessionSummary[] }) {
  if (sessions.length === 0) {
    return (
      <div className="text-center py-12 text-[var(--color-text-dim)]">
        <p className="text-lg">No sessions found.</p>
        <p className="text-sm mt-2">
          Upload your CPAP data on the <Link href="/" className="text-[var(--color-primary-light)] underline">home page</Link>.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {sessions.map((s) => (
        <Link
          key={s.id}
          href={`/sessions/${s.id}`}
          className="flex items-center gap-4 p-4 bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] hover:border-[var(--color-primary)] transition"
        >
          {/* Date */}
          <div className="w-36 shrink-0">
            <div className="font-medium">{formatDate(s.session_date)}</div>
          </div>

          {/* AHI Badge */}
          <div
            className="px-3 py-1 rounded-full text-sm font-bold"
            style={{
              backgroundColor: ahiColor(s.ahi) + "20",
              color: ahiColor(s.ahi),
            }}
          >
            AHI {s.ahi.toFixed(1)}
          </div>

          {/* Duration */}
          <div className="text-sm text-[var(--color-text-dim)]">
            {s.duration_hours.toFixed(1)}h
          </div>

          {/* Event pills */}
          <div className="flex gap-2 flex-1 flex-wrap">
            {Object.entries(s.event_counts).map(([type, count]) => (
              <span
                key={type}
                className="px-2 py-0.5 text-xs rounded bg-[var(--color-surface-2)]"
              >
                {type}: {count}
              </span>
            ))}
          </div>

          {/* Leak */}
          <div className="text-sm text-[var(--color-text-dim)] shrink-0">
            Leak: {s.leak_95.toFixed(0)} L/min
          </div>

          {/* Pressure */}
          <div className="text-sm text-[var(--color-text-dim)] shrink-0">
            P95: {s.pressure_95.toFixed(1)} cmH₂O
          </div>
        </Link>
      ))}
    </div>
  );
}
