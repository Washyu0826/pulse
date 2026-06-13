#!/usr/bin/env bash
# theme bake-off 第二輪：多語編碼器（mDeBERTa-v3）測跨語言轉移是否解掉語言錯配。
set -u; cd "$(dirname "$0")/.."
G=data/gold/gold.jsonl; S=data/silver/theme_capped.jsonl
COMMON="--task theme --gold $G --silver $S --base-model MoritzLaurer/mDeBERTa-v3-base-mnli-xnli --epochs 3 --batch-size 8 --offline --seed 42"
run () { local name="$1"; shift
  echo "===== [$(date +%H:%M:%S)] START $name =====" | tee -a logs/bakeoff/_status_ml.log
  py -3 scripts/train_classifier.py $COMMON "$@" > "logs/bakeoff/$name.log" 2>&1
  echo "===== [$(date +%H:%M:%S)] END $name rc=$? =====" | tee -a logs/bakeoff/_status_ml.log; }
run d1-mdeberta-effective --class-weights effective --out models/theme-d1-mdeberta-effective
run d2-mdeberta-none      --class-weights none      --out models/theme-d2-mdeberta-none
echo "===== [$(date +%H:%M:%S)] ALL DONE =====" | tee -a logs/bakeoff/_status_ml.log
