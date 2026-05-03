import { getSessions } from "@/lib/api";
import { AIClient } from "./ai-client";
import type { SessionSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AIPage() {
  let sessions: SessionSummary[] = [];
  let error: string | null = null;

  try {
    sessions = await getSessions();
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load sessions";
  }

  if (error) {
    return (
      <div className="text-[var(--color-danger)]">
        {error}
        <p className="text-sm text-[var(--color-text-dim)] mt-2">
          Make sure the backend is running at localhost:8000.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <Brain className="w-6 h-6 text-[var(--color-primary-light)]" />
        <h1 className="text-2xl font-bold">AI Sleep Assistant</h1>
      </div>
      <AIClient sessions={sessions} />
    </div>
  );
}

function Brain({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a8 8 0 0 0-8 8c0 3.4 2.1 6.3 5.1 7.6.3.1.5.4.5.7V20a1 1 0 0 0 1 1h2.8a1 1 0 0 0 1-1v-1.7c0-.3.2-.6.5-.7C17.9 16.3 20 13.4 20 10a8 8 0 0 0-8-8Z"/>
      <path d="M9 14h6"/><path d="M10 18h4"/>
    </svg>
  );
}
