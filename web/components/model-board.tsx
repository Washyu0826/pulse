import { ModelCard } from "@/components/model-card";
import { SectionStatus } from "@/components/section-status";
import { getModelDashboard } from "@/lib/api";

/** 6 模型即時看板（自帶 fetch；Suspense 邊界內串流）。 */
export async function ModelBoard() {
  const models = await getModelDashboard();
  if (!models.ok) {
    return <SectionStatus kind="error">無法載入模型看板，請確認 API 是否啟動</SectionStatus>;
  }
  if (models.data.length === 0) {
    return <SectionStatus kind="empty">尚無模型資料</SectionStatus>;
  }
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
      {models.data.map((m) => (
        <ModelCard key={m.slug} m={m} />
      ))}
    </div>
  );
}
