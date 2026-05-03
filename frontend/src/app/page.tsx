"use client";

import { useState, useCallback } from "react";
import { uploadCPAPData } from "@/lib/api";
import { Upload, CheckCircle, AlertCircle, Loader2 } from "lucide-react";

export default function HomePage() {
  const [status, setStatus] = useState<
    "idle" | "uploading" | "processing" | "done" | "error"
  >("idle");
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<{
    upload_id: string;
    num_sessions: number;
    device_info: Record<string, string>;
  } | null>(null);
  const [error, setError] = useState("");

  const handleUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      setStatus("uploading");
      setProgress(0);
      setError("");

      try {
        // Simulate progress while uploading
        const progressInterval = setInterval(() => {
          setProgress((p) => Math.min(p + 5, 90));
        }, 500);

        const res = await uploadCPAPData(file);
        clearInterval(progressInterval);
        setProgress(100);

        setStatus("done");
        setResult(res);
      } catch (err) {
        setStatus("error");
        setError(err instanceof Error ? err.message : "Upload failed");
      }
    },
    []
  );

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (!file) return;

      // Create a synthetic event
      const target = { files: [file] } as unknown as EventTarget;
      await handleUpload({
        target,
      } as React.ChangeEvent<HTMLInputElement>);
    },
    [handleUpload]
  );

  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] gap-8">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-3">
          CPAP Data Analyzer
        </h1>
        <p className="text-[var(--color-text-dim)] text-lg max-w-xl">
          Upload your ResMed SD card data (as a zip file) and get
          AI-powered insights about your sleep therapy.
        </p>
      </div>

      {/* Upload Zone */}
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        className="w-full max-w-lg border-2 border-dashed border-[var(--color-border)] rounded-xl p-12 text-center hover:border-[var(--color-primary)] transition-colors cursor-pointer bg-[var(--color-surface)]"
      >
        {status === "idle" && (
          <label className="cursor-pointer flex flex-col items-center gap-4">
            <Upload className="w-12 h-12 text-[var(--color-primary-light)]" />
            <span className="text-lg font-medium">
              Drop your CPAP data zip here
            </span>
            <span className="text-sm text-[var(--color-text-dim)]">
              or click to browse
            </span>
            <input
              type="file"
              accept=".zip"
              onChange={handleUpload}
              className="hidden"
            />
          </label>
        )}

        {status === "uploading" && (
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="w-12 h-12 text-[var(--color-primary-light)] animate-spin" />
            <span className="text-lg">Uploading & processing...</span>
            <div className="w-full bg-[var(--color-surface-2)] rounded-full h-2">
              <div
                className="bg-[var(--color-primary)] h-2 rounded-full transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {status === "done" && result && (
          <div className="flex flex-col items-center gap-4">
            <CheckCircle className="w-12 h-12 text-[var(--color-success)]" />
            <span className="text-lg font-medium">
              Successfully processed {result.num_sessions} nights!
            </span>
            {result.device_info.product_name && (
              <span className="text-sm text-[var(--color-text-dim)]">
                Device: {result.device_info.product_name} ({result.device_info.model_number})
              </span>
            )}
            <a
              href="/sessions"
              className="mt-2 px-6 py-2 bg-[var(--color-primary)] rounded-lg text-white font-medium hover:bg-[var(--color-primary-light)] transition"
            >
              View Sessions
            </a>
          </div>
        )}

        {status === "error" && (
          <div className="flex flex-col items-center gap-4">
            <AlertCircle className="w-12 h-12 text-[var(--color-danger)]" />
            <span className="text-lg font-medium">Upload failed</span>
            <span className="text-sm text-[var(--color-danger)]">{error}</span>
            <button
              onClick={() => setStatus("idle")}
              className="px-4 py-2 bg-[var(--color-surface-2)] rounded-lg text-sm"
            >
              Try again
            </button>
          </div>
        )}
      </div>

      {/* Instructions */}
      <div className="text-sm text-[var(--color-text-dim)] max-w-md text-center">
        <p className="font-medium mb-2">How to get your data:</p>
        <ol className="list-decimal list-inside space-y-1 text-left">
          <li>Remove the SD card from your ResMed machine</li>
          <li>Copy the entire SD card contents to your computer</li>
          <li>Zip the folder (the one containing DATALOG/, Identification.json, etc.)</li>
          <li>Upload the zip file here</li>
        </ol>
      </div>
    </div>
  );
}
