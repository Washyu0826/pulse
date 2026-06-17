# Pulse web（Next.js 14）部署用多階段建置。
# 產出最小化的 standalone server：只帶 .next/standalone + .next/static + public，
# 非 root 執行，不帶整包 node_modules（next.config.js 需開 output: 'standalone'）。
#
# build context = ./web（見 docker-compose.yml 的 web.build.context）。
#
# 選配 CA 注入：本機開發網路若有 TLS 攔截（如 Avast / 企業 MITM proxy），把該 proxy 根憑證
# 放到 web/certs/proxy-ca.crt（已 gitignore，不進版控）。下面會在 build 期掛入容器信任庫，
# 讓 npm / Next 的 HTTPS 請求能驗證鏈、正常抓套件與 SWC。乾淨 CI（無攔截）時此檔不存在 → 無副作用。

# ---- 1) deps：只裝相依，利於 layer 快取（package*.json 沒變就不重裝）----
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# certs/ 為選配 —— 用萬用字元結尾讓「不存在時」COPY 不報錯（至少 .gitkeep/憑證其一即可）。
# 乾淨 CI 無此目錄時，請保留一個空的 web/certs/.gitkeep（已隨 repo），否則移除此行即可。
COPY cert[s] ./certs/
# 若有 proxy CA：指給 Node（NODE_EXTRA_CA_CERTS，下面所有 node/next 子程序都吃）與 npm（cafile）。
# 不動系統信任庫（node:slim 無 ca-certificates 套件）—— 對 npm/Next 的 HTTPS 而言這兩者已足夠。
ENV NODE_EXTRA_CA_CERTS=/app/certs/proxy-ca.crt
RUN if [ -f /app/certs/proxy-ca.crt ]; then \
        npm config set cafile /app/certs/proxy-ca.crt; \
    fi
# 注意：package-lock.json 由 Windows 產生，缺 linux 平台 SWC 的 musl/emnapi 等條件依賴，
# 故 `npm ci`（嚴格比對鎖檔）會以 EUSAGE 失敗。改用 `npm install`：在 linux 容器內重新解析，
# 裝上正確平台的 @next/swc-linux-x64-gnu（含真 .node），build 不再於執行期上網抓 SWC。
RUN npm install --no-audit --no-fund \
    && test -n "$(find node_modules/@next/swc-linux-x64-gnu -name '*.node' -print -quit)"

# ---- 2) builder：帶原始碼跑 next build，產出 standalone ----
FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# 沒有 public/ 也照常 build（下面 runner 的 COPY 需要它存在 → 先建空資料夾）。
RUN mkdir -p public
# build 期不打 API（全 server component 在 runtime 才 fetch），故無需 build-time API_URL。
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---- 3) runner：最小執行期，非 root ----
FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# 非 root 使用者（standalone server 不需寫入專案目錄）。
RUN groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs nextjs

# standalone 輸出：server.js + 最小化 node_modules。static 與 public 需另外帶。
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

# standalone server 入口（Next 會把 server.js 放在 standalone 根）。
CMD ["node", "server.js"]
