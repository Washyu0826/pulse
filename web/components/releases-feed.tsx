import { ReleaseCard } from "@/components/release-card";
import { SectionStatus } from "@/components/section-status";
import { getRecentReleases } from "@/lib/api";

/** 最新發布（自帶 fetch；Suspense 邊界內串流）。 */
export async function ReleasesFeed() {
  const releases = await getRecentReleases(20);
  if (!releases.ok) {
    return <SectionStatus kind="error">無法載入發布事件，請確認 API 是否啟動</SectionStatus>;
  }
  if (releases.data.length === 0) {
    return <SectionStatus kind="empty">目前沒有新的 release 事件</SectionStatus>;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {releases.data.map((ev) => (
        <ReleaseCard key={ev.id} ev={ev} />
      ))}
    </div>
  );
}
