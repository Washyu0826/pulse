#!/usr/bin/env bash
# Sprint: theme 分類器 bake-off — 4 候選序列化訓練（單 GPU）。各自記 log，失敗續跑下一個。
set -u
cd "$(dirname "$0")/.."
G=data/gold/gold.jsonl
S=data/silver/theme_capped.jsonl
COMMON="--task theme --gold $G --silver $S --epochs 3 --batch-size 16 --offline --seed 42"
run () {
  local name="$1"; shift
  echo "===== [$(date +%H:%M:%S)] START $name =====" | tee -a logs/bakeoff/_status.log
  py -3 scripts/train_classifier.py $COMMON "$@" > "logs/bakeoff/$name.log" 2>&1
  local rc=$?
  echo "===== [$(date +%H:%M:%S)] END $name rc=$rc =====" | tee -a logs/bakeoff/_status.log
}
run c1-macbert-none      --base-model hfl/chinese-macbert-base --class-weights none      --out models/theme-c1-macbert-none
run c2-macbert-effective --base-model hfl/chinese-macbert-base --class-weights effective --out models/theme-c2-macbert-effective
run c3-macbert-inverse   --base-model hfl/chinese-macbert-base --class-weights inverse   --out models/theme-c3-macbert-inverse
run c4-bertbase-effective --base-model bert-base-chinese       --class-weights effective --out models/theme-c4-bertbase-effective
echo "===== [$(date +%H:%M:%S)] ALL DONE =====" | tee -a logs/bakeoff/_status.log
