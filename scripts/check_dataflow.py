"""
資料流健康檢查 —— 每日排程最後一步跑，回答「今天每個來源有沒有進貨」。

背景：2026-06-12 發現資料流靜默斷流兩天（Airflow 容器停了、DAG 全暫停、
排程錯過無補跑），所有環節都「看起來正常」。此腳本把斷流變成看得見的訊號：
低於門檻就在 stdout/log 印 ⚠️ 並以非零碼結束（daily_refresh 的 Step 會記 FAIL）。

用法：
    python scripts/check_dataflow.py            # 檢查近 24h
    python scripts/check_dataflow.py --hours 48
"""
import argparse
import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))

from api.database import AsyncSessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402

# 各來源近 24h 的最低進貨門檻（依 2026-06 實際量保守抓；0 = 選配來源不告警只報數）。
THRESHOLDS = {
    "hackernews": 20,
    "devto": 5,
    "threads": 5,   # 需 THREADS_SESSIONID；未登入模式常低於此 → 提醒補 cookie
    "ptt": 0,       # 選配（host 端腳本，尚未排程化）
    "lobsters": 0,
    "reddit": 0,    # DAG 暫停中（缺憑證）
}


async def main(hours: int) -> int:
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "select source, count(*) from posts "
                    "where fetched_at > now() - make_interval(hours => :h) group by 1"
                ),
                {"h": hours},
            )
        ).all()
    got = {r[0]: r[1] for r in rows}
    failures = []
    print(f"📊 資料流健康檢查（近 {hours}h）：")
    for src, minimum in THRESHOLDS.items():
        n = got.get(src, 0)
        if n < minimum:
            failures.append(src)
            print(f"  ⚠️ {src:<12} {n} 筆（門檻 {minimum}）")
        else:
            print(f"  ✅ {src:<12} {n} 筆")
    for src, n in got.items():  # 門檻表外的來源也報數
        if src not in THRESHOLDS:
            print(f"  ✅ {src:<12} {n} 筆（未設門檻）")
    if failures:
        print(f"⚠️ 斷流警告：{', '.join(failures)} —— 檢查 Airflow（docker ps、DAG 是否暫停）"
              "與 THREADS_SESSIONID。")
        return 1
    print("✅ 資料流正常。")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="資料流健康檢查")
    ap.add_argument("--hours", type=int, default=24)
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.hours)))
