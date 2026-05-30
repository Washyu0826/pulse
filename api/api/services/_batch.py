"""批次工具 —— UPSERT 分塊，避免超過 PostgreSQL 單語句 32767 個 bind 參數上限。"""
from collections.abc import Iterator, Sequence
from typing import TypeVar

T = TypeVar("T")

# 各表欄位數不同，取保守值；列數 × 欄位數需 < 32767。
# posts 13 欄、release_events ~10 欄、events ~8 欄 → 1000 列都安全。
DEFAULT_CHUNK = 1000


def chunked(seq: Sequence[T], size: int = DEFAULT_CHUNK) -> Iterator[Sequence[T]]:
    """把序列切成每塊最多 size 個。"""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
