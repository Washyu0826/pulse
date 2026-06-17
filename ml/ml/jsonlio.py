"""共用 JSONL 讀檔工具 —— 把散在 api/scripts 多處的「逐行 strip → json.loads
（壞行容錯跳過）→ 收集 dict」協定抽成單一實作。純函式、無重依賴，
api（已有 import ml 先例）與 scripts（sys.path 已加入 ml）皆可 import。

各 caller 的讀檔以外邏輯（staleness 警告、欄位映射、limit、缺檔 warning 等）
保留在原處；本模組只負責「安全地把 JSONL 變成 list[dict]」。
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


def read_jsonl(
    path: str | Path,
    *,
    validate: Callable[[dict[str, Any]], bool] | None = None,
) -> list[dict[str, Any]]:
    """讀 JSONL（一行一筆）→ list[dict]，缺檔 / 空行 / 壞行皆優雅略過。

    協定：
      - 檔案不存在 → 回 []（缺檔由 caller 視需要另記 warning）。
      - 逐行 strip，空行跳過。
      - json.loads；單行 JSON 解析失敗（JSONDecodeError）跳過該行，不讓整檔失敗。
      - 只收 dict（非 dict 的合法 JSON，如 list/str/number，跳過）。
      - validate（可選）：對每筆 dict 再做一次過濾，回 False 則跳過該筆。

    純函式、不改動輸入。回傳順序同檔案行序。
    """
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # 單行壞掉不該讓整檔失敗 —— 略過該行
        if not isinstance(rec, dict):
            continue
        if validate is not None and not validate(rec):
            continue
        out.append(rec)
    return out
