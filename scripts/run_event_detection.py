"""
手動執行 F8 事件偵測：讀 posts / release_events / sentiments → 偵測 → UPSERT 進 events。

實際邏輯已收斂到 workers/pipeline/events.py（與 Airflow event_detection DAG 共用，DRY）；
本腳本只是給開發者在本機手動觸發的薄包裝。

- discussion_spike：每模型每日討論量做穩健 z-score（median/MAD）偵測突增。
- launch：release_events 依 (模型, 日) 聚合成發布事件。
- sentiment_flip：近 14 天 vs 前 14 天口碑做雙比例 z 檢定。

可重跑（dedup_key 唯一）。

用法：cd api && uv run python ../scripts/run_event_detection.py
"""
import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "ml"))
sys.path.insert(0, str(_ROOT / "workers"))

from pipeline.events import run_event_detection  # noqa: E402


async def main() -> None:
    stats = await run_event_detection()
    print(
        f"🔎 偵測到：discussion_spike {stats['discussion_spike']} 筆、"
        f"launch {stats['launch']} 筆、sentiment_flip {stats['sentiment_flip']} 筆"
    )
    print("💾 UPSERT 統計：", {k: v for k, v in stats.items()
                            if k not in ("discussion_spike", "launch", "sentiment_flip")})


if __name__ == "__main__":
    asyncio.run(main())
