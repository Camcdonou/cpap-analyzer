import { getTrends, getOverview } from "@/lib/api";
import { TrendsClient } from "./trends-client";

export default async function TrendsPage() {
  let trends = null;
  let overview = null;
  let error = null;

  try {
    [trends, overview] = await Promise.all([getTrends(), getOverview()]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load trends";
  }

  if (error || !trends || !overview) {
    return (
      <div className="text-[var(--color-danger)]">
        {error || "Failed to load trends"}
        <p className="text-sm text-[var(--color-text-dim)] mt-2">
          Make sure the backend is running and data has been uploaded.
        </p>
      </div>
    );
  }

  return <TrendsClient trends={trends.data} overview={overview} />;
}
