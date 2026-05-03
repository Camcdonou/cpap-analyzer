import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CPAP Analyzer",
  description: "AI-powered CPAP sleep data analysis",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">
        <nav className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
            <a href="/" className="text-lg font-bold text-[var(--color-primary-light)]">
              😴 CPAP Analyzer
            </a>
            <a href="/sessions" className="text-sm text-[var(--color-text-dim)] hover:text-[var(--color-text)] transition">
              Sessions
            </a>
            <a href="/trends" className="text-sm text-[var(--color-text-dim)] hover:text-[var(--color-text)] transition">
              Trends
            </a>
            <a href="/ai" className="text-sm text-[var(--color-primary-light)] hover:text-[var(--color-text)] transition font-medium flex items-center gap-1">
              <span className="inline-block w-4 h-4">🤖</span> AI
            </a>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-4 py-6">
          {children}
        </main>
      </body>
    </html>
  );
}
