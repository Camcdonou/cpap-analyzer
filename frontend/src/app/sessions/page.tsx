import { getSessions } from "@/lib/api";
import type { SessionSummary } from "@/lib/api";
import { SessionList } from "./session-list";

export const dynamic = "force-dynamic";

export default async function SessionsPage() {
  let sessions: SessionSummary[] = [];
  let error: string | null = null;

  try {
    sessions = await getSessions();
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load sessions";
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Sleep Sessions</h1>
      {error ? (
        <div className="text-[var(--color-danger)]">
          {error}
          <p className="text-sm text-[var(--color-text-dim)] mt-2">
            Make sure the backend is running at localhost:8000 and data has been uploaded.
          </p>
        </div>
      ) : (
        <SessionList sessions={sessions} />
      )}
    </div>
  );
}
