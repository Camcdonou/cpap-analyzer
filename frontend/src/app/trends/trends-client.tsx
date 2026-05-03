"use client";

import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine,
  BarChart, Bar,
} from "recharts";
import type { TrendDataPoint } from "@/lib/api";

interface OverviewData {
  num_sessions: number;
  date_range: { first: string; last: string };
  avg_ahi: number;
  median_ahi: number;
  ahi_classification: Record<string, number>;
  avg_duration_hours: number;
  compliance_rate: number;
  avg_leak_95: number;
  high_leak_nights: number;
  total_events: Record<string, number>;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function TrendsClient({
  trends,
  overview,
}: {
  trends: TrendDataPoint[];
  overview: OverviewData;
}) {
  const chartData = trends.map((t) => ({
    ...t,
    dateLabel: formatDate(t.date),
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Trends & Overview</h1>

      {/* Overview Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
          <div className="text-sm text-[var(--color-text-dim)]">Total Nights</div>
          <div className="text-2xl font-bold">{overview.num_sessions}</div>
          <div className="text-xs text-[var(--color-text-dim)]">
            {overview.date_range.first} → {overview.date_range.last}
          </div>
        </div>
        <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
          <div className="text-sm text-[var(--color-text-dim)]">Average AHI</div>
          <div className="text-2xl font-bold" style={{ color: overview.avg_ahi < 5 ? "#22c55e" : overview.avg_ahi < 15 ? "#f59e0b" : "#ef4444" }}>
            {overview.avg_ahi.toFixed(1)}
          </div>
          <div className="text-xs text-[var(--color-text-dim)]">Median: {overview.median_ahi.toFixed(1)}</div>
        </div>
        <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
          <div className="text-sm text-[var(--color-text-dim)]">Avg Duration</div>
          <div className="text-2xl font-bold">{overview.avg_duration_hours.toFixed(1)}h</div>
          <div className="text-xs text-[var(--color-text-dim)]">
            Compliance: {(overview.compliance_rate * 100).toFixed(0)}% (≥4h)
          </div>
        </div>
        <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
          <div className="text-sm text-[var(--color-text-dim)]">Avg Leak 95%</div>
          <div className="text-2xl font-bold" style={{ color: overview.avg_leak_95 > 24 ? "#ef4444" : "#22c55e" }}>
            {overview.avg_leak_95.toFixed(0)} L/min
          </div>
          <div className="text-xs text-[var(--color-text-dim)]">
            {overview.high_leak_nights} high-leak nights
          </div>
        </div>
      </div>

      {/* AHI Classification */}
      <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
        <h3 className="font-medium mb-3">AHI Classification Distribution</h3>
        <div className="flex gap-4">
          {["normal", "mild", "moderate", "severe"].map((cls) => {
            const count = overview.ahi_classification[cls] || 0;
            const colors: Record<string, string> = {
              normal: "#22c55e",
              mild: "#f59e0b",
              moderate: "#ef4444",
              severe: "#dc2626",
            };
            const labels: Record<string, string> = {
              normal: "Normal (<5)",
              mild: "Mild (5-15)",
              moderate: "Moderate (15-30)",
              severe: "Severe (>30)",
            };
            return (
              <div key={cls} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: colors[cls] }} />
                <span className="text-sm">
                  {labels[cls]}: <strong>{count}</strong>
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* AHI Trend Chart */}
      <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
        <h3 className="font-medium mb-2">AHI Over Time</h3>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
            <XAxis dataKey="dateLabel" tick={{ fill: "#8888a0", fontSize: 10 }} interval={Math.max(1, Math.floor(chartData.length / 15))} />
            <YAxis tick={{ fill: "#8888a0", fontSize: 11 }} domain={[0, "auto"]} />
            <Tooltip
              contentStyle={{ backgroundColor: "#1a1a28", border: "1px solid #2a2a3a", borderRadius: 8 }}
            />
            <ReferenceLine y={5} stroke="#22c55e" strokeDasharray="3 3" label={{ value: "Normal", fill: "#22c55e", fontSize: 10 }} />
            <ReferenceLine y={15} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: "Mild", fill: "#f59e0b", fontSize: 10 }} />
            <Line type="monotone" dataKey="ahi" stroke="#6366f1" dot={{ r: 2 }} name="AHI" />
            <Line type="monotone" dataKey="oai" stroke="#ef4444" dot={false} name="OAI" />
            <Line type="monotone" dataKey="cai" stroke="#f59e0b" dot={false} name="CAI" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Duration & Leak Trends */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
          <h3 className="font-medium mb-2">Sleep Duration</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
              <XAxis dataKey="dateLabel" tick={{ fill: "#8888a0", fontSize: 10 }} interval={Math.max(1, Math.floor(chartData.length / 10))} />
              <YAxis tick={{ fill: "#8888a0", fontSize: 11 }} />
              <Tooltip contentStyle={{ backgroundColor: "#1a1a28", border: "1px solid #2a2a3a", borderRadius: 8 }} />
              <ReferenceLine y={4} stroke="#22c55e" strokeDasharray="3 3" label={{ value: "4h compliance", fill: "#22c55e", fontSize: 10 }} />
              <Bar dataKey="duration_hours" fill="#3b82f6" name="Hours" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
          <h3 className="font-medium mb-2">Leak Rate (95th %)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
              <XAxis dataKey="dateLabel" tick={{ fill: "#8888a0", fontSize: 10 }} interval={Math.max(1, Math.floor(chartData.length / 10))} />
              <YAxis tick={{ fill: "#8888a0", fontSize: 11 }} />
              <Tooltip contentStyle={{ backgroundColor: "#1a1a28", border: "1px solid #2a2a3a", borderRadius: 8 }} />
              <ReferenceLine y={24} stroke="#ef4444" strokeDasharray="3 3" label={{ value: "High leak", fill: "#ef4444", fontSize: 10 }} />
              <Line type="monotone" dataKey="leak_95" stroke="#f59e0b" dot={{ r: 2 }} name="Leak 95%" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Pressure Trend */}
      <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
        <h3 className="font-medium mb-2">Pressure (95th %) Over Time</h3>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
            <XAxis dataKey="dateLabel" tick={{ fill: "#8888a0", fontSize: 10 }} interval={Math.max(1, Math.floor(chartData.length / 15))} />
            <YAxis tick={{ fill: "#8888a0", fontSize: 11 }} domain={["auto", "auto"]} />
            <Tooltip contentStyle={{ backgroundColor: "#1a1a28", border: "1px solid #2a2a3a", borderRadius: 8 }} />
            <Line type="monotone" dataKey="pressure_95" stroke="#6366f1" dot={{ r: 2 }} name="Pressure 95%" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Total Event Summary */}
      <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
        <h3 className="font-medium mb-3">Total Events Summary</h3>
        <div className="flex gap-6">
          {Object.entries(overview.total_events).map(([type, count]) => {
            const names: Record<string, string> = {
              OA: "Obstructive Apnea",
              CA: "Central Apnea",
              H: "Hypopnea",
              A: "Apnea (Unspecified)",
              AR: "Arousal",
            };
            return (
              <div key={type} className="text-center">
                <div className="text-xl font-bold">{count}</div>
                <div className="text-xs text-[var(--color-text-dim)]">{names[type] || type}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
