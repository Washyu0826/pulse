# Pulse 每日刷新 —— 爬 Threads → DQC → 主題 → 熱詞 → 翻譯。給 Windows 工作排程器每日跑。
# 各步獨立 try/catch：單步失敗不擋後續，全部寫進 log。
# 前置：Docker 要開著（DB + airflow 容器）、Ollama 要開著（翻譯）、.env 有 THREADS_SESSIONID。
#
# 手動測試：powershell -ExecutionPolicy Bypass -File D:\pulse\scripts\daily_refresh.ps1

$ErrorActionPreference = "Continue"
$root = "D:\pulse"
$venvPy = "$root\.venv\Scripts\python.exe"          # selenium + DB（爬蟲）
$sysPy = "C:\Users\xiang\AppData\Local\Programs\Python\Python311\python.exe"  # GPU + jieba + httpx（ML）
$log = "$root\scripts\daily_refresh.log"

function Step($name, $block) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "[$ts] ▶ $name" | Tee-Object -FilePath $log -Append
  try { & $block 2>&1 | Tee-Object -FilePath $log -Append }
  catch { "[$ts] ✗ $name 失敗：$_" | Tee-Object -FilePath $log -Append }
}

Set-Location "$root\api"

Step "1/5 爬 Threads（每日 ~100 目標）" { & $venvPy "$root\scripts\try_threads.py" --headless --save --max-posts 40 --scroll 5 }
Step "2/5 DQC 品質檢查" { docker exec pulse-airflow-scheduler /opt/airflow/pulse-venv/bin/python -c "import asyncio; from pipeline.quality import run_dqc; print(asyncio.run(run_dqc()))" }
Step "3/5 主題分類" { & $sysPy "$root\scripts\backfill_themes.py" }
Step "4/5 本週熱詞" { & $sysPy "$root\scripts\backfill_keywords.py" --top 20 }
Step "5/5 英文貼翻譯" { & $sysPy "$root\scripts\backfill_translations.py" --days 7 --limit 60 }

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ✓ 每日刷新完成`n" | Tee-Object -FilePath $log -Append
