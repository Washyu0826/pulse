# Pulse 每日刷新 —— 爬 Threads → DQC → 情緒 → 主題 → 熱詞 → 翻譯。給 Windows 工作排程器每日跑。
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
  "[$ts] START $name" | Tee-Object -FilePath $log -Append
  $global:LASTEXITCODE = 0
  try {
    & $block 2>&1 | Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) {
      "[$ts] FAIL $name exit code: $LASTEXITCODE" | Tee-Object -FilePath $log -Append
    }
  }
  catch { "[$ts] FAIL $name error: $_" | Tee-Object -FilePath $log -Append }
}

Set-Location "$root\api"

Step "1/7 crawl Threads" { & $venvPy "$root\scripts\try_threads.py" --headless --save --max-posts 40 --scroll 5 }
Step "2/7 DQC quality" { docker exec pulse-airflow-scheduler /opt/airflow/pulse-venv/bin/python -c 'import asyncio; from pipeline.quality import run_dqc; print(asyncio.run(run_dqc()))' }
Step "3/7 sentiment" { & $sysPy "$root\scripts\backfill_sentiments.py" }
Step "4/7 theme" { & $sysPy "$root\scripts\backfill_themes.py" }
Step "5/7 weekly keywords" { & $sysPy "$root\scripts\backfill_keywords.py" --top 20 }
Step "6/7 translation" { & $sysPy "$root\scripts\backfill_translations.py" --days 7 --limit 60 }
# 電子報用系統 Python（matplotlib + diffusers + httpx + opencc）；需 .env 有 PULSE_SMTP_*。
# 不想每天跑 SD 題圖可加 --no-cover（快很多）。
Step "7/7 newsletter" { & $sysPy "$root\scripts\send_newsletter.py" }

$doneTs = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$doneTs] daily refresh complete`n" | Tee-Object -FilePath $log -Append
