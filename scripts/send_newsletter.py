"""
每日電子報 —— 從 DB 撈當日精選 → 本地 Qwen 摘要 → 組精緻 HTML（Swiss 版型，
圖表為純 HTML 條圖）→ Gmail SMTP 寄到信箱。全程免費 / 地端（[[prefer-local-llm]]）。

純函式（精選/組版/組信）在 ml/ml/newsletter.py，已單元測試；本檔只編排。

前置（系統 Python）：Ollama（本地 Qwen 摘要）。
SMTP 設定走環境變數 / .env：PULSE_SMTP_USER、PULSE_SMTP_APP_PASSWORD、PULSE_NEWSLETTER_TO。

用法：
    # 先預覽（不寄；存 HTML 到 out/）
    python scripts/send_newsletter.py --dry-run
    # 正式寄
    python scripts/send_newsletter.py
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "ml"))

# 改用 OS 信任庫，避開企業/校園 TLS 攔截導致的 CERTIFICATE_VERIFY_FAILED。
# 主要供 SMTP 寄送走 Windows 信任庫驗過 Avast MITM 重簽憑證（見下方 _send 註解）。
# best-effort：未裝 truststore（無攔截網路）就略過，OS 信任庫本來就正確。
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 — 注入失敗不該擋整支電子報
    pass

from ml.newsletter import (  # noqa: E402
    build_mime_message,
    render_html,
    select_highlights,
    sentiment_movers,
    theme_counts,
)

logger = logging.getLogger("pulse.newsletter")

_OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
_SUMMARY_MODEL = os.environ.get("PULSE_SUMMARY_MODEL", "qwen2.5:7b")


def _load_dotenv(path: Path) -> None:
    """把 .env 的 KEY=VALUE 載入 os.environ（不覆蓋已存在的）。供排程跑時取得 SMTP 設定。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.split("#", 1)[0].strip()
        if k:
            os.environ.setdefault(k, v)


# ----------------------- DB -----------------------
async def _fetch(days: int, min_quality: int) -> tuple[list[dict], list[str]]:
    # Heavy/DB imports stay lazy so the script module loads with only lightweight
    # deps (test_scripts_pure loads it via importlib in the no-DB CI env).
    from api.database import AsyncSessionLocal
    from api.models.posts import Post
    from api.models.sentiment import Sentiment
    from api.models.theme import Theme
    from api.models.translation import Translation
    from api.models.trending import TrendingKeyword
    from sqlalchemy import select

    # 今日視窗用「入庫時間」created_at 而非「原始發文時間」posted_at：
    # Threads 搜尋常撈出舊發文日的常青貼（posted_at 舊但今天才被我們收進來），
    # 用 posted_at 過濾會把當天大量入庫的 Threads（主力來源）幾乎全濾掉。
    # HN/devto 為即時貼文（posted_at≈created_at），改用 created_at 不受影響。
    since = datetime.now(UTC) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(
                    Post.id, Post.source, Post.title, Post.content, Post.url,
                    Post.score, Post.num_comments, Post.quality_score,
                    Theme.label.label("theme"), Sentiment.label.label("sentiment"),
                    Translation.title_zh, Translation.snippet_zh,
                )
                .outerjoin(Theme, Theme.post_id == Post.id)
                .outerjoin(Sentiment, Sentiment.post_id == Post.id)
                .outerjoin(Translation, Translation.post_id == Post.id)
                .where(Post.created_at >= since)
                .where((Post.quality_score.is_(None)) | (Post.quality_score >= min_quality))
                .order_by(Post.created_at.desc())
            )
        ).all()
        terms = (
            await session.execute(
                select(TrendingKeyword.term).order_by(TrendingKeyword.rank).limit(15)
            )
        ).scalars().all()

    # outerjoin themes/sentiments/translations 若單篇有多列髒資料（重跑分類沒清舊列），
    # 同一 post id 會出現多行 → theme_counts / scounts 翻倍、精選重複。
    # 每 post 的 theme/sentiment/translation 應唯一，故依 id 去重取第一筆（rows 已按
    # created_at desc 排序，保留第一筆即可）。
    posts = []
    seen_ids: set = set()
    for r in rows:
        if r.id in seen_ids:
            continue
        seen_ids.add(r.id)
        posts.append({
            "id": r.id, "source": r.source, "title": r.title, "content": r.content, "url": r.url,
            "score": r.score, "num_comments": r.num_comments, "quality_score": r.quality_score,
            "theme": r.theme, "sentiment": r.sentiment,
            "title_zh": r.title_zh, "snippet_zh": r.snippet_zh,
        })
    return posts, list(terms)


# ----------------------- 本地 Qwen 摘要 -----------------------
async def _summarize(titles: list[str]) -> str:
    from opencc import OpenCC

    if not titles:
        return "今日尚無足夠 AI 討論，明天見。"
    bullets = "\n".join(f"- {t}" for t in titles[:12])
    prompt = (
        "You are the editor of a Traditional-Chinese (Taiwan) daily AI newsletter. "
        "Write a natural 80-120 character summary IN TRADITIONAL CHINESE of today's key AI themes, "
        "based on these post titles. Keep product/model names in English. "
        "No list, no preamble, output only the summary:\n\n" + bullets
    )
    try:
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(
                f"{_OLLAMA}/api/generate",
                json={"model": _SUMMARY_MODEL, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.3}},
            )
            r.raise_for_status()
            out = (r.json().get("response") or "").strip().strip('"「」')
            return OpenCC("s2tw").convert(out) or _fallback_summary(titles)
    except Exception:  # noqa: BLE001 — 摘要失敗用 fallback，不該擋寄信
        logger.exception("Qwen 摘要失敗，改用 fallback")
        return _fallback_summary(titles)


def _fallback_summary(titles: list[str]) -> str:
    return f"今日整理 {len(titles)} 則 AI 討論，涵蓋新工具、使用方法、模型動態與風險等主題。"


# ----------------------- SMTP -----------------------
def _send(msg) -> None:
    import smtplib
    import ssl

    host = os.environ.get("PULSE_SMTP_HOST", "smtp.gmail.com")
    # 預設用 587 STARTTLS（見下方註解）。可用 PULSE_SMTP_PORT=465 強制走 SMTP_SSL。
    port = int(os.environ.get("PULSE_SMTP_PORT", "587"))
    user = os.environ["PULSE_SMTP_USER"]
    password = os.environ["PULSE_SMTP_APP_PASSWORD"]

    # 本機環境裝了 Avast Web/Mail Shield，會 MITM 攔截 SMTP TLS：
    #   * 465 SMTP_SSL：Avast 竟用「Untrusted Root」重簽 Gmail 憑證
    #     （issuer=CN=Avast Web/Mail Shield Untrusted Root），無論 Windows 信任庫
    #     或 certifi 都驗不過 → CERT_UNTRUSTED_ROOT / unable to get local issuer。
    #   * 587 STARTTLS：Avast 改用一般掃描根「CN=Avast Web/Mail Shield Root」重簽，
    #     該根已裝進 Windows 信任庫 → 用 truststore（Windows store）即可驗過。
    # 因此寄送走 truststore 的 Windows 信任庫：攔截環境吃 Avast 掃描根、
    # 未攔截環境吃 Gmail 公開根，兩者皆通；同時不動全域 truststore 注入，
    # 題圖（huggingface）下載能力完全保留。
    ctx = ssl.create_default_context()  # 全域已 inject_into_ssl → Windows 信任庫
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
            s.login(user, password)
            s.send_message(msg)


# ----------------------- 今日事件（忠實摘要 pipeline 產出的 JSONL）-----------------------
def _events_path() -> str:
    """今日事件來源檔路徑：環境變數 PULSE_EVENTS_FILE / EVENTS_FILE，預設 data/events_today.jsonl。
    （與 api/api/config.py 的 events_file 預設一致；由 scripts/run_event_pipeline.py 產出。）"""
    return os.environ.get(
        "PULSE_EVENTS_FILE",
        os.environ.get("EVENTS_FILE", str(_ROOT / "data" / "events_today.jsonl")),
    )


def _load_events_file() -> list[dict]:
    """讀今日事件 JSONL（一行一事件），給電子報「今日事件」區塊。
    缺檔 / 空行 / 壞行皆優雅略過回 []（無事件就不出該區塊，向後相容）。
    欄位（title/summary/citations/member_count/theme）即 render_today_events_section 所需。"""
    from ml.jsonlio import read_jsonl

    return read_jsonl(
        _events_path(),
        validate=lambda r: isinstance(r.get("summary"), str) and bool(r["summary"].strip()),
    )


# ----------------------- 議題演變 storylines（build_storylines.py 產出的 JSONL）-----------------------
def _storylines_path() -> str:
    """議題演變來源檔路徑：環境變數 PULSE_STORYLINES_FILE，預設 data/storylines.jsonl。
    （由 scripts/build_storylines.py 產出；每筆有 title/state/hotness/span_days/timeline/citations。）"""
    return os.environ.get("PULSE_STORYLINES_FILE", str(_ROOT / "data" / "storylines.jsonl"))


def _load_storylines_file() -> list[dict]:
    """讀議題演變 JSONL（一行一議題），驅動電子報「今日主秀」hero 的議題追蹤形態。
    缺檔 / 空行 / 壞行皆優雅略過回 []（hero 自動退回其他形態或不出，絕不報錯）。"""
    from ml.jsonlio import read_jsonl

    return read_jsonl(_storylines_path())


# ----------------------- 編排 -----------------------
async def main_async(args: argparse.Namespace) -> None:
    posts, trending = await _fetch(args.days, args.min_quality)
    print(f"📥 撈到 {len(posts)} 篇、熱詞 {len(trending)} 個")

    highlights = select_highlights(posts, per_theme=args.per_theme, min_quality=args.min_quality)
    movers = sentiment_movers(posts, k=3)
    tcounts = theme_counts(posts)
    scounts = {k: sum(1 for p in posts if p.get("sentiment") == k)
               for k in ("positive", "neutral", "negative")}

    titles = [(p.get("title_zh") or p.get("title") or "") for ps in highlights.values() for p in ps]
    summary = await _summarize(titles)

    # Swiss 版型不放封面題圖、也不再用彩色 matplotlib PNG（圖表改純 HTML 條圖，
    # 計數直接交給 render_html）→ 不再產任何內嵌圖片。
    events = _load_events_file()
    if events:
        print(f"🗂️  今日事件 {len(events)} 則（{Path(_events_path()).name}）")
    storylines = _load_storylines_file()
    if storylines:
        print(f"📈 議題演變 {len(storylines)} 條（{Path(_storylines_path()).name}）")
    html = render_html(
        day=date.today(), summary=summary, highlights=highlights, movers=movers,
        trending=trending, events=events,
        theme_counts=tcounts, sentiment_counts=scounts, storylines=storylines,
    )

    if args.dry_run:
        out = args.out
        out.mkdir(parents=True, exist_ok=True)
        (out / "newsletter.html").write_text(html, encoding="utf-8")
        print(f"📄 預覽已存：{out / 'newsletter.html'}。未寄送。")
        return

    to = args.to or os.environ.get("PULSE_NEWSLETTER_TO")
    if not to:
        sys.exit("❌ 缺收件人：--to 或環境變數 PULSE_NEWSLETTER_TO")
    msg = build_mime_message(
        subject=f"Pulse 每日 AI 情報 · {date.today().isoformat()}",
        sender=os.environ.get("PULSE_SMTP_USER", to),
        to=[to], html=html,
    )
    _send(msg)
    print(f"📧 已寄送到 {to}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _load_dotenv(_ROOT / ".env")
    ap = argparse.ArgumentParser(description="Pulse 每日電子報（地端摘要 + 圖表 + SD 題圖 + SMTP）")
    ap.add_argument("--to", default=None, help="收件人（預設環境變數 PULSE_NEWSLETTER_TO）")
    ap.add_argument("--days", type=int, default=1, help="撈最近 N 天的貼文")
    ap.add_argument("--min-quality", type=int, default=30)
    ap.add_argument("--per-theme", type=int, default=3, help="每主題精選幾篇")
    # Swiss 版型已不放 SD 題圖；--no-cover 保留為 no-op 僅為向後相容既有排程呼叫。
    ap.add_argument("--no-cover", action="store_true",
                    help="（已停用，no-op；Swiss 版型不再產 SD 題圖）")
    ap.add_argument("--dry-run", action="store_true", help="只存 HTML 預覽、不寄送")
    ap.add_argument("--out", type=Path, default=_ROOT / "out" / "newsletter", help="dry-run 輸出目錄")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
