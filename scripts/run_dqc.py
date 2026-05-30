"""
手動執行 DQC：評分所有未處理貼文 + 跨來源去重 → 寫回 posts.quality_score/quality_flags。

實際邏輯在 workers/pipeline/quality.py（與 Airflow data_quality DAG 共用，DRY）；本腳本只是薄包裝。

用法：cd api && uv run python ../scripts/run_dqc.py
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

from pipeline.quality import run_dqc  # noqa: E402


async def main() -> None:
    stats = await run_dqc()
    print("✅ DQC 完成")
    print(f"   評分貼文 = {stats['processed']}（高 {stats['high']} / 中 {stats['mid']} / 低 {stats['low']}）")
    print(f"   重複群組 = {stats['clusters']}，標記重複 = {stats['duplicates']} 篇")


if __name__ == "__main__":
    asyncio.run(main())
