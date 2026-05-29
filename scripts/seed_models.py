"""
Seed 6 個預設監測模型（idempotent，可重複跑）。

用法（在 repo 根目錄）：
    cd api && uv run python ../scripts/seed_models.py
或：
    python scripts/seed_models.py   # 需先 pip install api 依賴並設好 DATABASE_URL
"""
import asyncio
import sys
from pathlib import Path

# Windows console 預設 cp950，印中文 / emoji 會 crash → 強制 UTF-8。
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 讓腳本能 import api 套件
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api.database import AsyncSessionLocal  # noqa: E402
from api.models.models import Model  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

# slug 要與 workers/crawlers/reddit.py 的 MODEL_KEYWORDS 一致
SEED_MODELS = [
    {
        "slug": "gpt",
        "name": "GPT-5 / ChatGPT",
        "company": "OpenAI",
        "role": "霸主",
        "aliases": ["gpt", "chatgpt", "openai"],
    },
    {
        "slug": "claude",
        "name": "Claude",
        "company": "Anthropic",
        "role": "技術派最愛",
        "aliases": ["claude", "anthropic"],
    },
    {
        "slug": "gemini",
        "name": "Gemini",
        "company": "Google",
        "role": "多模態強",
        "aliases": ["gemini", "bard"],
    },
    {
        "slug": "grok",
        "name": "Grok",
        "company": "xAI",
        "role": "話題王",
        "aliases": ["grok", "xai"],
    },
    {
        "slug": "llama",
        "name": "Llama",
        "company": "Meta",
        "role": "開源代表",
        "aliases": ["llama"],
    },
    {
        "slug": "deepseek",
        "name": "DeepSeek",
        "company": "DeepSeek",
        "role": "中國攻擊者",
        "aliases": ["deepseek"],
    },
]


async def main() -> None:
    async with AsyncSessionLocal() as session:
        stmt = pg_insert(Model).values(SEED_MODELS)
        # 已存在就更新顯示用欄位（slug 不變）
        stmt = stmt.on_conflict_do_update(
            index_elements=[Model.slug],
            set_={
                "name": stmt.excluded.name,
                "company": stmt.excluded.company,
                "role": stmt.excluded.role,
                "aliases": stmt.excluded.aliases,
            },
        )
        await session.execute(stmt)
        await session.commit()
    print(f"✅ Seed 完成：{len(SEED_MODELS)} 個模型")


if __name__ == "__main__":
    asyncio.run(main())
