# 額外根憑證（TLS 攔截環境用）

若你的網路有 **TLS 攔截**（企業/校園 proxy 重簽憑證），Airflow 容器內的爬蟲對外 HTTPS
會踩 `CERTIFICATE_VERIFY_FAILED` —— 因為攔截 proxy 的根 CA 在你的 **OS 信任庫**，但不在
Linux 容器的信任庫裡（容器內 truststore 也救不了，它讀的是容器自己的 store）。

## 解法

把你機器信任的根 CA 匯出成 `.crt`（PEM）放進**這個資料夾**，重新 build image 即可——
`Dockerfile.airflow` 會把本資料夾的 `*.crt` 內容**併進**容器的
`/etc/ssl/certs/ca-certificates.crt`（系統信任庫 bundle），之後容器內 truststore / httpx
就會信任攔截 proxy。空目錄（正常網路）為 no-op。

```powershell
# Windows：把本機信任庫（含攔截 proxy 的根 CA）匯出成一份 bundle
$out = New-Object System.Collections.ArrayList
foreach ($store in @('Cert:\LocalMachine\Root','Cert:\LocalMachine\CA',
                     'Cert:\CurrentUser\Root','Cert:\CurrentUser\CA')) {
  foreach ($c in Get-ChildItem $store -ErrorAction SilentlyContinue) {
    [void]$out.Add("-----BEGIN CERTIFICATE-----")
    [void]$out.Add([Convert]::ToBase64String($c.RawData,'InsertLineBreaks'))
    [void]$out.Add("-----END CERTIFICATE-----")
  }
}
Set-Content workers\ca-certs\local.crt -Value ($out -join "`n") -Encoding ascii

# 重 build + 重啟
docker compose build airflow-scheduler
docker compose up -d airflow-scheduler airflow-webserver
```

`*.crt` 已被 `.gitignore` 排除（機器相關、勿入庫）。正常（無攔截）網路不需要這步，
資料夾留空即可，`update-ca-certificates` 對空目錄無作用。
