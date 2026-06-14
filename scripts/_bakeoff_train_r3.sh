#!/usr/bin/env bash
# round-3：用語言對齊的中文 silver（+混合）重訓 mDeBERTa，測能否終於勝過 zero-shot。
set -u; cd "$(dirname "$0")/.."
G=data/gold/gold.jsonl
BASE="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
COMMON="--task theme --gold $G --base-model $BASE --epochs 3 --batch-size 8 --class-weights effective --offline --seed 42"
run () { local name="$1"; local silver="$2"; shift 2
  echo "===== [$(date +%H:%M:%S)] START $name =====" | tee -a logs/bakeoff/_status_r3.log
  py -3 scripts/train_classifier.py $COMMON --silver "$silver" --out "models/$name" > "logs/bakeoff/$name.log" 2>&1
  echo "===== [$(date +%H:%M:%S)] END $name rc=$? =====" | tee -a logs/bakeoff/_status_r3.log; }
run theme-e1-zh-effective  data/silver/theme_zh.jsonl
run theme-e2-mix-effective data/silver/theme_mix.jsonl
echo "===== [$(date +%H:%M:%S)] ALL DONE =====" | tee -a logs/bakeoff/_status_r3.log
