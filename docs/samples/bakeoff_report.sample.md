# 摘要品質 Bake-off 報告

> 兩套摘要器在同一事件集上的忠實度配對比較（Offline Evaluation；非線上 A/B）。
> 事件數（配對）：3

## 1. 系統分數摘要

| 系統 | mean | median | min | max | n |
|------|------|--------|-----|-----|---|
| systemA_head18 | 0.8333 | 1.0000 | 0.5000 | 1.0000 | 3 |
| systemB_head10 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 3 |

## 2. 配對均值差與 bootstrap 95% CI

Δ = mean(systemA_head18) − mean(systemB_head10) = **-0.1667**

配對 bootstrap 95% CI：[-0.5000, +0.0000]

## 3. 逐事件勝率

| 結果 | 場數 |
|------|------|
| systemA_head18 勝 | 0 |
| systemB_head10 勝 | 1 |
| 平手 | 2 |
| 合計 | 3 |

systemA_head18 勝率：0.00%

## 5. 決策

**決策鐵則：配對差的 bootstrap CI 跨 0（含 0）≠ 一場勝利。** 只有 CI 整段不含 0 才宣稱該系統顯著較佳；否則視為「打平 / 證據不足」。

決策：**no_winner (CI overlaps 0)**
