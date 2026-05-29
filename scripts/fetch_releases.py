"""
手動測試腳本：抓 HF / GitHub 發布事件 → UPSERT 進 release_events → 印統計。

零 key（GitHub 可選 GITHUB_TOKEN 提高額度）。Week 7 會被 Airflow DAG 取代。

前置：docker compose up -d db；alembic upgrade head；python scripts/seed_models.py

用法：
    cd api && uv run python ../scripts/fetch_releases.py            # HF + GitHub
    cd api && uv run python ../scripts/fetch_releases.py --source huggingface
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 企業 / 校園 TLS 攔截：改用 OS 信任庫。best-effort。
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "workers"))

from api.database import AsyncSessionLocal  # noqa: E402
from api.services.releases import upsert_release_events  # noqa: E402
from crawlers.github import crawl_github  # noqa: E402
from crawlers.huggingface import crawl_huggingface  # noqa: E402


async def main(source: str) -> None:
    rows: list[dict] = []
    if source in ("all", "huggingface"):
        async for ev in crawl_huggingface():
            rows.append(ev)
    if source in ("all", "github"):
        async for ev in crawl_github(token=os.environ.get("GITHUB_TOKEN")):
            rows.append(ev)

    print(f"📥 抓到 {len(rows)} 筆發布事件")

    async with AsyncSessionLocal() as session:
        stats = await upsert_release_events(session, rows)

    print("💾 UPSERT 統計：")
    print(f"   received = {stats['received']}")
    print(f"   skipped  = {stats['skipped']}")
    print(f"   upserted = {stats['upserted']}")

    dist: dict[str, int] = {}
    for r in rows:
        key = f"{r['source']}/{r.get('model')}"
        dist[key] = dist.get(key, 0) + 1
    print("📊 來源/模型分佈：", dict(sorted(dist.items())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", choices=["all", "huggingface", "github"], default="all",
    )
    asyncio.run(main(parser.parse_args().source))
