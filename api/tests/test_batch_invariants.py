"""
靜態不變式：UPSERT 分塊大小 × 欄位數必須 < PG 的 32767 bind 參數上限。

不需 DB。鎖住此不變式 —— 之後有人調大 chunk 或加欄位導致超限會立刻被測出。
"""
from api.services._batch import DEFAULT_CHUNK
from api.services.events import _EVENT_COLUMNS
from api.services.posts import _ASSOC_CHUNK, _POST_CHUNK, _POST_COLUMNS
from api.services.releases import _RE_COLUMNS

PG_PARAM_LIMIT = 32767


def test_posts_chunk_under_limit():
    assert _POST_CHUNK * len(_POST_COLUMNS) < PG_PARAM_LIMIT


def test_assoc_chunk_under_limit():
    assert _ASSOC_CHUNK * 2 < PG_PARAM_LIMIT  # post_models 2 欄


def test_release_chunk_under_limit():
    # +1 為迴圈內加上的 model_id
    assert DEFAULT_CHUNK * (len(_RE_COLUMNS) + 1) < PG_PARAM_LIMIT


def test_event_chunk_under_limit():
    assert DEFAULT_CHUNK * (len(_EVENT_COLUMNS) + 1) < PG_PARAM_LIMIT
