"use client";

import { useState } from "react";
import Link from "next/link";
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import type { SessionDetail, EventItem } from "@/lib/api";
import { generateReport, askQuestion } from "@/lib/api";
import { ArrowLeft, Brain, MessageCircle, Loader2, Send } from "lucide-react";
import ReactMarkdown from "react-markdown";

interface Signals {
  [key: string]: {
    values: number[];
    sampling_rate: number;
    unit: string;
  };
}

function ahiColor(ahi: number): string {
  if (ahi < 5) return "#22c55e";
  if (ahi < 15) return "#f59e0b";
  if (ahi < 30) return "#ef4444";
  return "#ef4444";
}

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.floor(minutes % 60);
  return `${h}h ${m}m`;
}

export function SessionDetailClient({
  session,
  events,
  signals,
}: {
  session: SessionDetail;
  events: EventItem[];
  signals: Signals;
}) {
  const [report, setReport] = useState<string | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [question, setQuestion] = useState("");
  const [qaHistory, setQaHistory] = useState<{ q: string; a: string }[]>([]);
  const [qaLoading, setQaLoading] = useState(false);

  const durationMin = session.duration_hours * 60;

  // Build chart data from signals
  function buildChartData(signalName: string) {
    const sig = signals[signalName];
    if (!sig) return [];

    const intervalSec = 60; // 1min resolution
    return sig.values.map((v, i) => ({
      time: formatTime(i * intervalSec / 60),
      timeMin: i * (intervalSec / 60),
      value: v,
    }));
  }

  // Build events timeline data
  function buildEventsTimeline() {
    if (!events.length) return [];

    return events
      .filter((e) => e.event_type !== "UNK")
      .map((e) => ({
        time: formatTime(e.onset_seconds / 60),
        timeMin: e.onset_seconds / 60,
        type: e.event_type,
        duration: e.duration_seconds,
      }));
  }

  async function handleGenerateReport() {
    setReportLoading(true);
    try {
      const r = await generateReport(session.id);
      setReport(r.summary_text);
    } catch (e) {
      setReport("Error generating report: " + (e instanceof Error ? e.message : "Unknown error"));
    }
    setReportLoading(false);
  }

  async function handleAsk() {
    if (!question.trim()) return;
    setQaLoading(true);
    const q = question;
    setQuestion("");
    try {
      const res = await askQuestion(q, [session.id]);
      setQaHistory((prev) => [...prev, { q, a: res.answer }]);
    } catch (e) {
      setQaHistory((prev) => [
        ...prev,
        { q, a: "Error: " + (e instanceof Error ? e.message : "Unknown error") },
      ]);
    }
    setQaLoading(false);
  }

  const eventTimeline = buildEventsTimeline();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href="/sessions" className="text-[var(--color-text-dim)] hover:text-[var(--color-text)]">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold">
          {new Date(session.session_date + "T00:00:00").toLocaleDateString("en-US", {
            weekday: "long",
            month: "long",
            day: "numeric",
            year: "numeric",
          })}
        </h1>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="AHI"
          value={session.ahi.toFixed(1)}
          sublabel={session.ahi < 5 ? "Normal" : session.ahi < 15 ? "Mild" : session.ahi < 30 ? "Moderate" : "Severe"}
          color={ahiColor(session.ahi)}
        />
        <StatCard label="Duration" value={session.duration_hours.toFixed(1) + "h"} sublabel={formatTime(durationMin)} />
        <StatCard label="Leak 95%" value={session.leak_95.toFixed(0) + " L/min"} sublabel={session.leak_95 > 24 ? "High" : "OK"} color={session.leak_95 > 24 ? "#ef4444" : undefined} />
        <StatCard label="Pressure 95%" value={session.pressure_95.toFixed(1)} sublabel="cmH₂O" />
      </div>

      {/* AHI Breakdown */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MiniStat label="Obstructive (OAI)" value={session.oai.toFixed(1)} />
        <MiniStat label="Central (CAI)" value={session.cai.toFixed(1)} />
        <MiniStat label="Hypopnea (HI)" value={session.hi.toFixed(1)} />
        <MiniStat label="EPR Level" value={session.epr_level.toString()} />
        <MiniStat label="Pressure Range" value={`${session.min_pressure}-${session.max_pressure} cmH₂O`} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pressure Chart */}
        {signals.pressure && (
          <ChartCard title="Therapy Pressure" unit="cmH₂O">
            <AreaChart data={buildChartData("pressure")}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
              <XAxis dataKey="timeMin" tick={{ fill: "#8888a0", fontSize: 11 }} tickFormatter={(v) => formatTime(v)} />
              <YAxis tick={{ fill: "#8888a0", fontSize: 11 }} domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1a1a28", border: "1px solid #2a2a3a", borderRadius: 8 }}
                labelFormatter={(v) => formatTime(Number(v))}
              />
              <Area type="monotone" dataKey="value" stroke="#6366f1" fill="#6366f120" name="Pressure" />
            </AreaChart>
          </ChartCard>
        )}

        {/* Leak Chart */}
        {signals.leak && (
          <ChartCard title="Leak Rate" unit="L/min">
            <AreaChart data={buildChartData("leak")}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
              <XAxis dataKey="timeMin" tick={{ fill: "#8888a0", fontSize: 11 }} tickFormatter={(v) => formatTime(v)} />
              <YAxis tick={{ fill: "#8888a0", fontSize: 11 }} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1a1a28", border: "1px solid #2a2a3a", borderRadius: 8 }}
                labelFormatter={(v) => formatTime(Number(v))}
              />
              <Area type="monotone" dataKey="value" stroke="#f59e0b" fill="#f59e0b20" name="Leak" />
            </AreaChart>
          </ChartCard>
        )}

        {/* Respiratory Rate */}
        {signals.resp_rate && (
          <ChartCard title="Respiratory Rate" unit="bpm">
            <LineChart data={buildChartData("resp_rate")}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
              <XAxis dataKey="timeMin" tick={{ fill: "#8888a0", fontSize: 11 }} tickFormatter={(v) => formatTime(v)} />
              <YAxis tick={{ fill: "#8888a0", fontSize: 11 }} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1a1a28", border: "1px solid #2a2a3a", borderRadius: 8 }}
                labelFormatter={(v) => formatTime(Number(v))}
              />
              <Line type="monotone" dataKey="value" stroke="#22c55e" dot={false} name="RR" />
            </LineChart>
          </ChartCard>
        )}

        {/* Tidal Volume */}
        {signals.tidal_volume && (
          <ChartCard title="Tidal Volume" unit="mL">
            <LineChart data={buildChartData("tidal_volume")}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
              <XAxis dataKey="timeMin" tick={{ fill: "#8888a0", fontSize: 11 }} tickFormatter={(v) => formatTime(v)} />
              <YAxis tick={{ fill: "#8888a0", fontSize: 11 }} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1a1a28", border: "1px solid #2a2a3a", borderRadius: 8 }}
                labelFormatter={(v) => formatTime(Number(v))}
              />
              <Line type="monotone" dataKey="value" stroke="#3b82f6" dot={false} name="TV" />
            </LineChart>
          </ChartCard>
        )}
      </div>

      {/* Events Timeline */}
      {eventTimeline.length > 0 && (
        <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
          <h3 className="text-lg font-semibold mb-3">Sleep Events Timeline</h3>
          <div className="flex flex-wrap gap-2">
            {eventTimeline.map((evt, i) => (
              <span
                key={i}
                className="px-2 py-1 text-xs rounded"
                style={{
                  backgroundColor:
                    evt.type === "OA" ? "#ef444430" :
                    evt.type === "CA" ? "#f59e0b30" :
                    evt.type === "H"  ? "#3b82f630" :
                    evt.type === "AR" ? "#8b5cf630" :
                    "#6b728030",
                  color:
                    evt.type === "OA" ? "#ef4444" :
                    evt.type === "CA" ? "#f59e0b" :
                    evt.type === "H"  ? "#3b82f6" :
                    evt.type === "AR" ? "#8b5cf6" :
                    "#6b7280",
                }}
                title={`${evt.type} at ${evt.time}, ${evt.duration}s`}
              >
                {evt.type} @ {evt.time}
              </span>
            ))}
          </div>

          {/* Events Table */}
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-dim)] border-b border-[var(--color-border)]">
                <th className="text-left py-1">Time</th>
                <th className="text-left py-1">Type</th>
                <th className="text-left py-1">Duration</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-b border-[var(--color-border)]/30">
                  <td className="py-1">{formatTime(e.onset_seconds / 60)}</td>
                  <td className="py-1">
                    <span
                      className="px-1.5 py-0.5 rounded text-xs"
                      style={{
                        backgroundColor:
                          e.event_type === "OA" ? "#ef444430" :
                          e.event_type === "CA" ? "#f59e0b30" :
                          e.event_type === "H"  ? "#3b82f630" :
                          e.event_type === "AR" ? "#8b5cf630" : "#6b728030",
                      }}
                    >
                      {eventTypeName(e.event_type)}
                    </span>
                  </td>
                  <td className="py-1">{e.duration_seconds.toFixed(0)}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* AI Report Section */}
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <Brain className="w-5 h-5 text-[var(--color-primary-light)]" />
          <h3 className="text-lg font-semibold">AI Analysis</h3>
        </div>

        {!report && !reportLoading && (
          <button
            onClick={handleGenerateReport}
            className="px-5 py-2.5 bg-[var(--color-primary)] rounded-xl text-white font-medium hover:bg-[var(--color-primary-light)] transition"
          >
            Generate AI Report
          </button>
        )}

        {reportLoading && (
          <div className="flex items-center gap-2 text-[var(--color-text-dim)]">
            <Loader2 className="w-4 h-4 animate-spin text-[var(--color-primary-light)]" />
            Generating AI analysis...
          </div>
        )}

        {report && (
          <div className="prose-custom text-sm leading-relaxed">
            <ReactMarkdown>{report}</ReactMarkdown>
          </div>
        )}
      </div>

      {/* Q&A Section */}
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <MessageCircle className="w-5 h-5 text-[var(--color-primary-light)]" />
          <h3 className="text-lg font-semibold">Ask About This Night</h3>
        </div>

        <div className="space-y-4 mb-4">
          {qaHistory.map((qa, i) => (
            <div key={i} className="space-y-2">
              <div className="text-sm font-medium">
                {qa.q}
              </div>
              <div className="prose-custom text-sm leading-relaxed">
                <ReactMarkdown>{qa.a}</ReactMarkdown>
              </div>
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAsk()}
            placeholder="Ask about this night's sleep data..."
            className="flex-1 px-3 py-2 bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-lg text-sm focus:outline-none focus:border-[var(--color-primary)]"
          />
          <button
            onClick={handleAsk}
            disabled={qaLoading}
            className="px-4 py-2 bg-[var(--color-primary)] rounded-lg text-white text-sm font-medium hover:bg-[var(--color-primary-light)] transition disabled:opacity-50"
          >
            {qaLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Helper Components ──────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sublabel,
  color,
}: {
  label: string;
  value: string;
  sublabel?: string;
  color?: string;
}) {
  return (
    <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
      <div className="text-sm text-[var(--color-text-dim)]">{label}</div>
      <div className="text-2xl font-bold" style={color ? { color } : undefined}>
        {value}
      </div>
      {sublabel && (
        <div className="text-xs text-[var(--color-text-dim)]">{sublabel}</div>
      )}
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-3">
      <div className="text-xs text-[var(--color-text-dim)]">{label}</div>
      <div className="text-sm font-medium">{value}</div>
    </div>
  );
}

function ChartCard({
  title,
  unit,
  children,
}: {
  title: string;
  unit: string;
  children: React.ReactElement;
}) {
  return (
    <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-4">
      <div className="flex justify-between items-center mb-2">
        <h3 className="font-medium">{title}</h3>
        <span className="text-xs text-[var(--color-text-dim)]">{unit}</span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        {children}
      </ResponsiveContainer>
    </div>
  );
}

function eventTypeName(type: string): string {
  const names: Record<string, string> = {
    OA: "Obstructive Apnea",
    CA: "Central Apnea",
    H: "Hypopnea",
    A: "Apnea",
    AR: "Arousal",
    RERA: "RERA",
    CS: "Cheyne-Stokes",
  };
  return names[type] || type;
}
