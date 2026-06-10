"""
每日電子報 —— 從 DB 撈當日精選 → 本地 Qwen 摘要 → matplotlib 繁中圖表 + 地端 SD 題圖 →
組精緻 HTML → Gmail SMTP 寄到信箱。全程免費 / 地端（[[prefer-local-llm]]）。

純函式（精選/組版/組信）在 ml/ml/newsletter.py 與 ml/ml/charts.py，已單元測試；本檔只編排。

前置（系統 Python）：matplotlib（圖表）、diffusers+torch（題圖，可 --no-cover 跳過）、Ollama（摘要）。
SMTP 設定走環境變數 / .env：PULSE_SMTP_USER、PULSE_SMTP_APP_PASSWORD、PULSE_NEWSLETTER_TO。

用法：
    # 先預覽（不寄；存 HTML + 圖到 out/，也不跑 SD）
    python scripts/send_newsletter.py --dry-run --no-cover
    # 正式寄（含地端 SD 題圖）
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

from ml.newsletter import (  # noqa: E402
    build_mime_message,
    cover_prompt,
    render_html,
    select_highlights,
    sentiment_movers,
    theme_counts,
)
from sqlalchemy import select  # noqa: E402

logger = logging.getLogger("pulse.newsletter")

_OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
_SUMMARY_MODEL = os.environ.get("PULSE_SUMMARY_MODEL", "qwen2.5:7b")
_COVER_MODEL = os.environ.get("PULSE_COVER_MODEL", "segmind/SSD-1B")
_COVER_NEG = (
    "text, words, letters, typography, caption, watermark, signature, logo, ui, numbers, "
    "gibberish text, photo, photorealistic, 3d render, cluttered, low quality, blurry, deformed"
)


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
    from api.database import AsyncSessionLocal
    from api.models.posts import Post
    from api.models.sentiment import Sentiment
    from api.models.theme import Theme
    from api.models.translation import Translation
    from api.models.trending import TrendingKeyword

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
                .where(Post.posted_at >= since)
                .where((Post.quality_score.is_(None)) | (Post.quality_score >= min_quality))
                .order_by(Post.posted_at.desc())
            )
        ).all()
        terms = (
            await session.execute(
                select(TrendingKeyword.term).order_by(TrendingKeyword.rank).limit(15)
            )
        ).scalars().all()

    posts = [
        {
            "id": r.id, "source": r.source, "title": r.title, "content": r.content, "url": r.url,
            "score": r.score, "num_comments": r.num_comments, "quality_score": r.quality_score,
            "theme": r.theme, "sentiment": r.sentiment,
            "title_zh": r.title_zh, "snippet_zh": r.snippet_zh,
        }
        for r in rows
    ]
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


# ----------------------- 地端 SD 題圖 -----------------------
def _generate_cover(prompt: str, seed: int) -> bytes | None:
    try:
        import io

        import torch
        from diffusers import AutoPipelineForText2Image
    except ImportError:
        logger.warning("未安裝 diffusers/torch，跳過題圖（可 --no-cover 明確略過）")
        return None
    try:
        kwargs = {"torch_dtype": torch.float16, "use_safetensors": True}
        try:
            pipe = AutoPipelineForText2Image.from_pretrained(_COVER_MODEL, variant="fp16", **kwargs)
        except Exception:  # noqa: BLE001 — 無 fp16 變體就退一般
            pipe = AutoPipelineForText2Image.from_pretrained(_COVER_MODEL, **kwargs)
        pipe.enable_model_cpu_offload()  # 8GB 4060：勿再 .to('cuda')
        try:
            pipe.enable_vae_tiling()
        except Exception:  # noqa: BLE001
            pass
        pipe.set_progress_bar_config(disable=True)
        gen = torch.Generator(device="cuda").manual_seed(seed) if torch.cuda.is_available() else None
        img = pipe(prompt=prompt, negative_prompt=_COVER_NEG, width=1024, height=576,
                   num_inference_steps=30, guidance_scale=7.0, generator=gen).images[0]
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        logger.info("題圖完成（%s）", _COVER_MODEL)
        return buf.getvalue()
    except Exception:  # noqa: BLE001 — 題圖失敗不該擋寄信
        logger.exception("題圖生成失敗，跳過")
        return None


# ----------------------- SMTP -----------------------
def _send(msg) -> None:
    import smtplib
    import ssl

    host = os.environ.get("PULSE_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("PULSE_SMTP_PORT", "465"))
    user = os.environ["PULSE_SMTP_USER"]
    password = os.environ["PULSE_SMTP_APP_PASSWORD"]
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=ctx) as s:
        s.login(user, password)
        s.send_message(msg)


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

    # 圖表（matplotlib）
    images: dict[str, bytes] = {}
    chart_cids: dict[str, str] = {}
    try:
        from ml.charts import sentiment_bar_png, theme_bar_png

        images["theme@pulse"] = theme_bar_png(tcounts)
        chart_cids["theme"] = "theme@pulse"
        images["sentiment@pulse"] = sentiment_bar_png(scounts)
        chart_cids["sentiment"] = "sentiment@pulse"
    except Exception:  # noqa: BLE001 — 無 matplotlib 就不放圖
        logger.exception("圖表產生失敗（未裝 matplotlib？），略過圖表")

    # 題圖（地端 SD）
    cover_cid = None
    if not args.no_cover:
        lead = next(iter(highlights), None)  # 第一個有貼文的主題當主導
        cover = _generate_cover(cover_prompt(trending, lead_theme=lead), seed=args.seed)
        if cover:
            images["cover@pulse"] = cover
            cover_cid = "cover@pulse"

    html = render_html(
        day=date.today(), summary=summary, highlights=highlights, movers=movers,
        trending=trending, cover_cid=cover_cid, chart_cids=chart_cids,
    )

    if args.dry_run:
        out = args.out
        out.mkdir(parents=True, exist_ok=True)
        (out / "newsletter.html").write_text(html, encoding="utf-8")
        for cid, data in images.items():
            (out / f"{cid.split('@')[0]}.png").write_bytes(data)
        print(f"📄 預覽已存：{out / 'newsletter.html'}（圖 {len(images)} 張）。未寄送。")
        return

    to = args.to or os.environ.get("PULSE_NEWSLETTER_TO")
    if not to:
        sys.exit("❌ 缺收件人：--to 或環境變數 PULSE_NEWSLETTER_TO")
    msg = build_mime_message(
        subject=f"Pulse 每日 AI 情報 · {date.today().isoformat()}",
        sender=os.environ.get("PULSE_SMTP_USER", to),
        to=[to], html=html, images=images,
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
    ap.add_argument("--no-cover", action="store_true", help="跳過地端 SD 題圖（快、省資源）")
    ap.add_argument("--seed", type=int, default=20260607, help="SD 固定 seed（封面風格一致）")
    ap.add_argument("--dry-run", action="store_true", help="只存 HTML+圖預覽、不寄送")
    ap.add_argument("--out", type=Path, default=_ROOT / "out" / "newsletter", help="dry-run 輸出目錄")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
