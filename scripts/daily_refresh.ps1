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

# 失敗步驟彙整：每步仍照跑（單步失敗不擋後續），但任何一步失敗就讓整體以非零碼結束、
# 並在結尾印一份醒目 FAIL 摘要 —— 排程器/人眼才看得出「這次跑壞了」（2026-06-12 教訓）。
$failedSteps = @()

function Step($name, $block) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "[$ts] START $name" | Tee-Object -FilePath $log -Append
  $global:LASTEXITCODE = 0
  $failed = $false
  try {
    & $block 2>&1 | Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) {
      $failed = $true
      "[$ts] FAIL $name exit code: $LASTEXITCODE" | Tee-Object -FilePath $log -Append
    }
  }
  catch {
    $failed = $true
    "[$ts] FAIL $name error: $_" | Tee-Object -FilePath $log -Append
  }
  if ($failed) { $script:failedSteps += $name }
}

Set-Location "$root\api"

Step "1/8 crawl Threads" { & $venvPy "$root\scripts\try_threads.py" --headless --save --max-posts 40 --scroll 5 }
Step "2/8 DQC quality" { docker exec pulse-airflow-scheduler /opt/airflow/pulse-venv/bin/python -c 'import asyncio; from pipeline.quality import run_dqc; print(asyncio.run(run_dqc()))' }
Step "3/8 sentiment" { & $sysPy "$root\scripts\backfill_sentiments.py" }
Step "4/8 theme" { & $sysPy "$root\scripts\backfill_themes.py" }
Step "5/8 weekly keywords" { & $sysPy "$root\scripts\backfill_keywords.py" --top 20 }
Step "6/8 translation" { & $sysPy "$root\scripts\backfill_translations.py" --days 7 --limit 60 }
# 電子報用系統 Python（matplotlib + diffusers + httpx + opencc）；需 .env 有 PULSE_SMTP_*。
# 不想每天跑 SD 題圖可加 --no-cover（快很多）。
Step "7/8 newsletter" { & $sysPy "$root\scripts\send_newsletter.py" }
# 資料流健康檢查：各來源近 24h 進貨低於門檻就 FAIL 進 log（斷流要看得見，2026-06-12 教訓）。
Step "8/8 dataflow health" { & $sysPy "$root\scripts\check_dataflow.py" }

$doneTs = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
if ($failedSteps.Count -gt 0) {
  # 醒目 FAIL 摘要 + 非零碼：讓工作排程器把這次標記為失敗，斷流/壞步驟不再無聲。
  "========================================" | Tee-Object -FilePath $log -Append
  "[$doneTs] daily refresh FAILED —— $($failedSteps.Count) 步失敗：$($failedSteps -join ', ')" |
    Tee-Object -FilePath $log -Append
  "========================================`n" | Tee-Object -FilePath $log -Append
  exit 1
}
"[$doneTs] daily refresh complete (all steps OK)`n" | Tee-Object -FilePath $log -Append
exit 0
