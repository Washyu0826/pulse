# Threads 定期累積爬取（每 30 分鐘一輪，由 Windows 排程觸發）。
# Threads 單輪量小、搜尋每次浮出不同貼文 → 靠定期重跑 + UPSERT 冪等慢慢累積在地繁中 AI 訊號。
# 鎖檔避免與前一輪（或手動跑的那輪）重疊：同帳號同時多開易觸發 Threads 限流/封鎖。

$ErrorActionPreference = 'Stop'
Set-Location 'D:\pulse'
$lock = Join-Path $env:TEMP 'pulse_threads.lock'

# 鎖檔存在且 < 25 分鐘 → 上一輪還在跑，本輪跳過
if (Test-Path $lock) {
    $age = (Get-Date) - (Get-Item $lock).LastWriteTime
    if ($age.TotalMinutes -lt 25) {
        Write-Output "上一輪仍在跑（鎖檔 $([int]$age.TotalMinutes) 分鐘），本輪跳過。"
        exit 0
    }
}

New-Item -ItemType File -Path $lock -Force | Out-Null
try {
    $env:ENVIRONMENT = 'production'
    python scripts/try_threads.py --headless --max-posts 40 --scroll 5 --save
} finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
