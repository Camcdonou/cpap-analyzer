"use client";

import { useState, useRef, useEffect } from "react";
import { askQuestion } from "@/lib/api";
import { Brain, Loader2, Send } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { SessionSummary } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export function AIClient({ sessions }: { sessions: SessionSummary[] }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  async function handleSend() {
    if (!input.trim() || loading) return;

    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);

    try {
      // Don't send session IDs — let the backend send the full trend table
      // (all 216 nights fit in 256k context)
      const res = await askQuestion(userMsg, []);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Error: " + (e instanceof Error ? e.message : "AI request failed. Check that OPENAI_API_KEY is set in backend/.env"),
        },
      ]);
    }
    setLoading(false);
  }

  return (
    <div className="flex flex-col h-[calc(100vh-200px)]">
      {/* Chat messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-6 mb-4 pr-2">
        {messages.length === 0 && (
          <div className="text-center py-12 space-y-4">
            <Brain className="w-16 h-16 text-[var(--color-primary-light)] mx-auto opacity-50" />
            <h2 className="text-xl font-semibold">Ask about your sleep data</h2>
            <p className="text-[var(--color-text-dim)] max-w-md mx-auto">
              I have access to all {sessions.length} nights of your CPAP data.
              Ask me anything — AHI trends, event patterns, leak issues, pressure questions.
            </p>
            <div className="flex flex-wrap justify-center gap-2 mt-4">
              {[
                "How is my therapy going overall?",
                "Am I having more obstructive or central apneas?",
                "Is my mask leaking too much?",
                "What's my AHI trend over the last month?",
              ].map((q) => (
                <button
                  key={q}
                  onClick={() => setInput(q)}
                  className="px-3 py-1.5 text-sm bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-lg hover:border-[var(--color-primary)] transition"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
            <div
              className={
                m.role === "user"
                  ? "max-w-[80%] px-4 py-3 rounded-2xl rounded-br-sm bg-[var(--color-primary)] text-white"
                  : "max-w-[90%]"
              }
            >
              {m.role === "assistant" && (
                <div className="flex items-center gap-1.5 mb-2 text-xs text-[var(--color-text-dim)]">
                  <Brain className="w-3.5 h-3.5 text-[var(--color-primary-light)]" />
                  <span>AI</span>
                </div>
              )}
              <div className={m.role === "user" ? "text-sm" : "prose-custom text-sm leading-relaxed"}>
                {m.role === "user" ? (
                  m.content
                ) : (
                  <ReactMarkdown>{m.content}</ReactMarkdown>
                )}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex items-center gap-2 px-2 text-[var(--color-text-dim)]">
            <Loader2 className="w-4 h-4 animate-spin text-[var(--color-primary-light)]" />
            <span className="text-sm">Thinking...</span>
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="flex gap-2 border-t border-[var(--color-border)] pt-4">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Ask about your CPAP data..."
          className="flex-1 px-4 py-3 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl text-sm focus:outline-none focus:border-[var(--color-primary)]"
          disabled={loading}
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim()}
          className="px-4 py-3 bg-[var(--color-primary)] rounded-xl text-white hover:bg-[var(--color-primary-light)] transition disabled:opacity-30"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
