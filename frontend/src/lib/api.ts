/** API client for CPAP Analyzer backend */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Types ────────────────────────────────────────────────────────────────
export interface UploadResponse {
  upload_id: string;
  status: string;
  num_sessions: number;
  device_info: Record<string, string>;
  error_message?: string;
}

export interface SessionSummary {
  id: number;
  session_date: string;
  duration_hours: number;
  ahi: number;
  oai: number;
  cai: number;
  hi: number;
  leak_95: number;
  pressure_95: number;
  event_counts: Record<string, number>;
}

export interface SessionDetail extends SessionSummary {
  mask_on_seconds: number;
  mask_off_seconds: number;
  leak_50: number;
  leak_max: number;
  pressure_50: number;
  pressure_max: number;
  epap_95: number;
  rr_50: number;
  mv_50: number;
  tv_50: number;
  set_pressure: number;
  min_pressure: number;
  max_pressure: number;
  epr_level: number;
  csr_percent: number;
  source_files: Record<string, string>;
  device_info: Record<string, unknown>;
  settings_info: Record<string, unknown>;
}

export interface EventItem {
  id: number;
  session_id: number;
  event_type: string;
  onset_seconds: number;
  duration_seconds: number;
  raw_text: string;
}

export interface SignalDataResponse {
  signal_name: string;
  sampling_rate: number;
  unit: string;
  values: number[];
  values_1min?: number[];
  values_5min?: number[];
}

export interface TrendDataPoint {
  date: string;
  ahi: number;
  oai: number;
  cai: number;
  hi: number;
  leak_95: number;
  pressure_95: number;
  duration_hours: number;
  event_counts: Record<string, number>;
}

export interface OverviewData {
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

export interface AIReport {
  id: number;
  session_id: number | null;
  report_type: string;
  summary_text: string;
  key_findings: string[];
  recommendations: string[];
  model_version: string;
}

// ── API Functions ────────────────────────────────────────────────────────
export async function uploadCPAPData(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed: ${text}`);
  }
  return res.json();
}

export async function getSessions(): Promise<SessionSummary[]> {
  return fetchAPI("/sessions");
}

export async function getSession(id: number): Promise<SessionDetail> {
  return fetchAPI(`/sessions/${id}`);
}

export async function getSessionEvents(id: number): Promise<EventItem[]> {
  return fetchAPI(`/sessions/${id}/events`);
}

export async function getSessionSignals(
  id: number,
  signalNames?: string[],
  resolution: string = "auto"
): Promise<SignalDataResponse[]> {
  const params = new URLSearchParams();
  if (signalNames) params.set("signal_names", signalNames.join(","));
  params.set("resolution", resolution);
  return fetchAPI(`/sessions/${id}/signals?${params}`);
}

export async function getTrends(): Promise<{ metric: string; data: TrendDataPoint[] }> {
  return fetchAPI("/trends");
}

export async function getOverview(): Promise<OverviewData> {
  return fetchAPI("/overview");
}

export async function generateReport(
  sessionId: number,
  reportType: string = "nightly"
): Promise<AIReport> {
  return fetchAPI("/ai/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      report_type: reportType,
    }),
  });
}

export async function askQuestion(
  question: string,
  contextSessionIds: number[] = []
): Promise<{ answer: string; sources: string[] }> {
  return fetchAPI("/ai/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      context_session_ids: contextSessionIds,
    }),
  });
}
