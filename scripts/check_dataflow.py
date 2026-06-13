"""
資料流健康檢查 —— 每日排程最後一步跑，回答「今天每個來源有沒有進貨」。

背景：2026-06-12 發現資料流靜默斷流兩天（Airflow 容器停了、DAG 全暫停、
排程錯過無補跑），所有環節都「看起來正常」。此腳本把斷流變成看得見的訊號：
低於門檻就在 stdout/log 印 ⚠️ 並以非零碼結束（daily_refresh 的 Step 會記 FAIL）。

用法：
    python scripts/check_dataflow.py            # 日終：檢查近 24h 進貨量是否達門檻
    python scripts/check_dataflow.py --hours 48
    python scripts/check_dataflow.py --lag-only # 盤中：只看「每來源最後抓取距今幾分鐘」，
                                                #       超過 MAX_LAG_MINUTES 就告警（早於日終發現斷流）
    python scripts/check_dataflow.py --json     # 機器可讀輸出（給排程/告警串接）

盤中偵測（建議後續）：把 `--lag-only` 用 Airflow 或 Windows 工作排程器每 1–2h 跑一次，
就能在「晚上日終檢查」之前發現某來源中途斷流（2026-06-12 那次拖了兩天才被發現）。
（本輪不新增 DAG —— 只把訊號暴露出來，排程化留作 follow-up。）
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))

from api.database import AsyncSessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402

# 各來源近 24h 的最低進貨門檻（日終量檢查用）。
#
# 來源 / 調整方式：數字依 2026-06 各來源「正常日」的實際進貨量保守抓（取觀測下緣再打折，
#   避免假陽性）。要重新校準時：跑 `--hours 24` 看連續幾天的實際 n，把門檻設在穩定下緣的 ~50%。
#   新增來源時在此補一列；選配/暫停來源設 0（只報數、不告警）。
THRESHOLDS = {
    "hackernews": 20,
    "devto": 5,
    "threads": 5,   # 需 THREADS_SESSIONID；未登入模式常低於此 → 提醒補 cookie
    "ptt": 0,       # 選配（host 端腳本，尚未排程化）
    "lobsters": 0,
    "reddit": 0,    # DAG 暫停中（缺憑證）
}

# 盤中 lag 告警閾值（分鐘）：某「有門檻」的主力來源最後一筆抓取距今超過此值 → 視為斷流疑慮。
# 來源 / 調整方式：主力來源（hackernews/devto/threads）目前約每數小時一批；抓 240 分鐘（4h）
#   當寬鬆上限，給排程抖動留餘裕。要更敏感就調小；門檻為 0 的選配來源不納入 lag 告警。
MAX_LAG_MINUTES = 240


async def _fetch_counts(hours: int) -> dict[str, int]:
    """各來源近 N 小時進貨筆數。"""
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
    return {r[0]: r[1] for r in rows}


async def _fetch_lag_minutes() -> dict[str, float]:
    """各來源「最後一筆抓取距今幾分鐘」—— 盤中偵測斷流用（無時間窗，看全表最新）。"""
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "select source, "
                    "extract(epoch from (now() - max(fetched_at))) / 60 as lag_min "
                    "from posts group by 1"
                )
            )
        ).all()
    return {r[0]: float(r[1]) for r in rows}


def _emit_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=str))


async def check_lag(as_json: bool = False) -> int:
    """盤中：只看 lag（最後抓取距今分鐘數）。有門檻的主力來源 lag 超標 → 非零碼。"""
    lag = await _fetch_lag_minutes()
    failures = []
    detail = {}
    for src, minimum in THRESHOLDS.items():
        if minimum <= 0:  # 選配/暫停來源不納入 lag 告警
            continue
        m = lag.get(src)
        stale = m is None or m > MAX_LAG_MINUTES
        detail[src] = None if m is None else round(m, 1)
        if stale:
            failures.append(src)
    if as_json:
        _emit_json({
            "check": "lag", "max_lag_minutes": MAX_LAG_MINUTES,
            "lag_minutes": detail, "stale_sources": failures, "ok": not failures,
        })
        return 1 if failures else 0
    print(f"⏱️ 盤中資料 lag 檢查（門檻 {MAX_LAG_MINUTES} 分鐘）：")
    for src, minimum in THRESHOLDS.items():
        if minimum <= 0:
            continue
        m = lag.get(src)
        if m is None:
            print(f"  ⚠️ {src:<12} 從無資料")
        elif m > MAX_LAG_MINUTES:
            print(f"  ⚠️ {src:<12} 最後抓取 {m:.0f} 分鐘前（超過 {MAX_LAG_MINUTES}）")
        else:
            print(f"  ✅ {src:<12} 最後抓取 {m:.0f} 分鐘前")
    if failures:
        print(f"⚠️ lag 告警：{', '.join(failures)} 中途可能斷流 —— 檢查 Airflow / 該來源 DAG。")
        return 1
    print("✅ 各來源 lag 正常。")
    return 0


async def main(hours: int, as_json: bool = False) -> int:
    """日終：近 N 小時進貨量達門檻檢查（同時帶上 lag 供觀測）。"""
    got = await _fetch_counts(hours)
    lag = await _fetch_lag_minutes()
    failures = []
    counts_detail = {}
    for src, minimum in THRESHOLDS.items():
        n = got.get(src, 0)
        counts_detail[src] = n
        if n < minimum:
            failures.append(src)
    if as_json:
        _emit_json({
            "check": "daily", "hours": hours, "counts": got,
            "lag_minutes": {k: round(v, 1) for k, v in lag.items()},
            "below_threshold": failures, "ok": not failures,
        })
        return 1 if failures else 0
    print(f"📊 資料流健康檢查（近 {hours}h）：")
    for src, minimum in THRESHOLDS.items():
        n = got.get(src, 0)
        lag_s = f"，最後 {lag[src]:.0f} 分鐘前" if src in lag else "，無資料"
        if n < minimum:
            print(f"  ⚠️ {src:<12} {n} 筆（門檻 {minimum}{lag_s}）")
        else:
            print(f"  ✅ {src:<12} {n} 筆（門檻 {minimum}{lag_s}）")
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
    ap.add_argument("--lag-only", action="store_true",
                    help="盤中模式：只檢查各來源最後抓取距今分鐘數（不看 24h 量）")
    ap.add_argument("--json", action="store_true", help="機器可讀 JSON 輸出")
    args = ap.parse_args()
    if args.lag_only:
        sys.exit(asyncio.run(check_lag(as_json=args.json)))
    sys.exit(asyncio.run(main(args.hours, as_json=args.json)))
