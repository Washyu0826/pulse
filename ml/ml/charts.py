"""
電子報圖表 —— matplotlib 產 PNG bytes（premium 風格 + 繁中字體）。全地端、免費。

依圖表研究：去 chartjunk（無框線/刻度）、單一強調色、2x DPI、繁中字體註冊（避免 tofu □）、
固定淺色卡底（暗色模式安全）。重依賴 matplotlib 只在函式內載入 → 本檔可被 import 而不強制裝。
水平長條最適合窄欄 + 長中文標籤。
"""
from __future__ import annotations

import io
from pathlib import Path

__all__ = ["theme_bar_png", "sentiment_bar_png"]

# 與電子報視覺一致的色票
_ACCENT = "#2563eb"
_ACCENT2 = "#f97316"
_INK = "#111827"
_MUTED = "#6b7280"
_CARD = "#ffffff"

# 繁中字體候選（Windows 內建 msjh 優先；否則專案內 Noto；都沒有則 DejaVu（中文會 tofu 但不 crash））。
_CJK_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msjh.ttc",
    r"C:\Windows\Fonts\msjhbd.ttc",
    str(Path(__file__).resolve().parent / "fonts" / "NotoSansCJKtc-Regular.otf"),
]
_FONT_NAME: str | None = None


def _ensure_style():
    """設好 Agg backend + premium rcParams + 繁中字體（addfont 不持久 → 每次確保）。回傳 pyplot。"""
    global _FONT_NAME
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import font_manager as fm
    from matplotlib import pyplot as plt

    if _FONT_NAME is None:
        _FONT_NAME = "DejaVu Sans"
        for p in _CJK_FONT_CANDIDATES:
            if Path(p).exists():
                try:
                    fm.fontManager.addfont(p)
                    _FONT_NAME = fm.FontProperties(fname=p).get_name()
                    break
                except Exception:  # noqa: BLE001 — 字體載入失敗就用 fallback
                    continue
    plt.rcParams.update({
        "figure.facecolor": _CARD, "axes.facecolor": _CARD, "savefig.facecolor": _CARD,
        "savefig.dpi": 200, "font.family": [_FONT_NAME], "axes.unicode_minus": False,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.spines.left": False, "axes.spines.bottom": False,
        "xtick.major.size": 0, "ytick.major.size": 0,
        "text.color": _INK, "axes.labelcolor": _MUTED,
        "ytick.color": _INK, "xtick.color": _MUTED, "ytick.labelsize": 10,
    })
    return plt


def _hbar(labels: list[str], values: list[int], *, title: str, highlight: bool = True) -> bytes:
    """水平長條（最大值在上、可強調首位）→ PNG bytes。"""
    plt = _ensure_style()
    pairs = sorted(zip(labels, values, strict=True), key=lambda x: x[1])  # 升冪 → barh 最大在上
    labels = [p[0] for p in pairs]
    values = [p[1] for p in pairs]
    fig, ax = plt.subplots(figsize=(3.2, max(1.4, 0.42 * len(labels) + 0.6)))
    colors = [_ACCENT] * len(values)
    if highlight and values:
        colors[-1] = _ACCENT2  # 強調當日第一名
    bars = ax.barh(labels, values, color=colors, height=0.62)
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=10)
    ax.set_xticks([])
    mx = max(values) if values else 1
    for b, v in zip(bars, values, strict=True):
        ax.text(b.get_width() + mx * 0.02, b.get_y() + b.get_height() / 2,
                str(v), va="center", ha="left", color=_MUTED, fontsize=9)
    ax.margins(x=0.16)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)  # 釋放記憶體（每日長跑腳本必須）
    return buf.getvalue()


def theme_bar_png(counts: dict[str, int]) -> bytes:
    """今日主題分布水平長條（含其他）。counts: {主題: 篇數}。"""
    items = [(k, v) for k, v in counts.items() if v > 0] or [("（今日無資料）", 0)]
    return _hbar([k for k, _ in items], [v for _, v in items], title="今日主題分布")


def sentiment_bar_png(counts: dict[str, int]) -> bytes:
    """今日口碑分布（正/中/負）。counts: {'positive'/'neutral'/'negative': 篇數}。"""
    order = (("positive", "正面"), ("neutral", "中性"), ("negative", "負面"))
    return _hbar([zh for _, zh in order], [int(counts.get(k, 0)) for k, _ in order],
                 title="今日口碑分布", highlight=False)
