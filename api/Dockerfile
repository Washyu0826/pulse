FROM python:3.11-slim

WORKDIR /app

# 選配 CA 注入：本機開發網路若有 TLS 攔截（Avast / 企業 MITM proxy），把 proxy 根憑證放到
# api/certs/proxy-ca.crt（已 gitignore，不入庫）。下面把它併入容器系統信任庫（python:slim 內含
# ca-certificates 與 update-ca-certificates），讓 pip / uv / requests / openssl 的 HTTPS 都驗得過，
# 不會 CERTIFICATE_VERIFY_FAILED。乾淨 CI（無攔截）時此檔不存在 → 整段 no-op，無副作用。
# repo 內保有 certs/.gitkeep，故 COPY certs/ 在乾淨 checkout 也成立。
COPY certs ./certs/
RUN if [ -f /app/certs/proxy-ca.crt ]; then \
        cp /app/certs/proxy-ca.crt /usr/local/share/ca-certificates/proxy-ca.crt \
        && update-ca-certificates; \
    fi
# 讓 pip / requests 走系統信任庫（update-ca-certificates 產出的 bundle）。
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# 系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 用 uv 安裝（比 pip 快很多）
RUN pip install --no-cache-dir uv

# 複製 dependency 檔
COPY pyproject.toml ./

# 安裝依賴
RUN uv pip install --system --no-cache .

# 複製程式碼
COPY api/ ./api/
COPY alembic/ ./alembic/
COPY alembic.ini ./

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
