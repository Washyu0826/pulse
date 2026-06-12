"""
收藏 → 知識材料包 端點。

收藏在前端（localStorage），呼叫端把選取的貼文 POST 上來 → 依主題分組 → 地端 Ollama 蒸成
可重用材料（失敗自動退回確定性條列）→ 回 markdown + sources.jsonl 供下載。

重用 monorepo 的 ml 純函式（與 scripts 同作法：把 D:\\pulse\\ml 加進 path）。LLM 為阻塞式
httpx 呼叫 → 丟 threadpool，避免卡住 async event loop。
"""
import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

# 重用 ml 純函式（collection_pack / summarize 的 Ollama 工廠）。
_ML = Path(__file__).resolve().parents[3] / "ml"
if str(_ML) not in sys.path:
    sys.path.insert(0, str(_ML))

from ml.collection_pack import build_pack  # noqa: E402
from ml.summarize import build_ollama_generate_fn  # noqa: E402

router = APIRouter()

_PACK_MODEL = os.environ.get("PULSE_PACK_MODEL", "qwen2.5:7b")
_MAX_POSTS = 100  # 防止超大 prompt / 過長生成


class PackPost(BaseModel):
    id: int | None = None
    title: str = ""
    title_zh: str | None = None
    snippet: str = ""
    snippet_zh: str | None = None
    source: str = ""
    url: str | None = None
    models: list[str] = Field(default_factory=list)
    theme: str = ""
    posted_at: str | None = None


class PackRequest(BaseModel):
    posts: list[PackPost]
    distill: bool = True  # True=地端 LLM 蒸餾；False=確定性條列（快、不需 Ollama）
    title: str = "收藏知識材料包"


class PackResponse(BaseModel):
    markdown: str
    sources_jsonl: str
    themes: list[dict]
    n_posts: int


@router.post("/collection/pack", response_model=PackResponse)
async def make_collection_pack(req: PackRequest) -> PackResponse:
    """把選取的收藏蒸成知識材料包。distill=True 用地端 Ollama；連不上時各主題自動退回確定性條列。"""
    if not req.posts:
        raise HTTPException(status_code=400, detail="沒有選取任何收藏。")
    if len(req.posts) > _MAX_POSTS:
        raise HTTPException(status_code=400, detail=f"一次最多 {_MAX_POSTS} 篇，請減少選取。")

    posts = [p.model_dump() for p in req.posts]
    generate_fn = None
    if req.distill:
        try:
            generate_fn = build_ollama_generate_fn(model=_PACK_MODEL)
        except Exception:
            generate_fn = None  # 缺 httpx 等 → 退確定性

    # build_pack 內含阻塞式 Ollama 呼叫 → threadpool 執行。
    pack = await run_in_threadpool(build_pack, posts, generate_fn, title=req.title)
    return PackResponse(**pack)
