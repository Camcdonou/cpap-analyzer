import { getSession, getSessionEvents, getSessionSignals } from "@/lib/api";
import { SessionDetailClient } from "./session-detail-client";

export default async function SessionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const sessionId = parseInt(id, 10);

  let session = null;
  let events = [];
  let signals: Record<string, { values: number[]; sampling_rate: number; unit: string }> = {};
  let error = null;

  try {
    session = await getSession(sessionId);
    events = await getSessionEvents(sessionId);
    
    // Fetch key signals for charting
    const signalNames = ["pressure", "leak", "epap", "resp_rate", "minute_vent", "tidal_volume", "mask_pressure"];
    const signalData = await getSessionSignals(sessionId, signalNames, "1min");
    
    for (const s of signalData) {
      signals[s.signal_name] = {
        values: s.values_1min || s.values,
        sampling_rate: s.sampling_rate,
        unit: s.unit,
      };
    }
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load session";
  }

  if (error || !session) {
    return (
      <div className="text-[var(--color-danger)]">
        {error || "Session not found"}
      </div>
    );
  }

  return <SessionDetailClient session={session} events={events} signals={signals} />;
}
