"""
應用設定 - 用 pydantic-settings 從環境變數載入。
"""
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    environment: str = "development"
    log_level: str = "INFO"

    # Database
    # host 埠 5433（避開本機 PostgreSQL）；用 127.0.0.1 避免 Windows IPv6 解析問題。
    database_url: str = "postgresql+asyncpg://pulse:pulse@127.0.0.1:5433/pulse"
    database_url_sync: str = "postgresql://pulse:pulse@127.0.0.1:5433/pulse"

    # Reddit API
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "pulse/0.1"

    # X / Twitter（選配 best-effort 來源，無官方免費 API → 用 twscrape + 帳號 cookie）。
    # 從 x.com DevTools → Application → Cookies 取 auth_token / ct0；建議用次要帳號。缺則略過。
    x_auth_token: str = ""
    x_ct0: str = ""
    x_username: str = ""

    # Threads（選配 best-effort 來源，Selenium 爬，有登入牆）。從 threads.net DevTools →
    # Application → Cookies 取 sessionid（與 Instagram 共用）；建議用次要帳號。缺則退化為未登入。
    threads_sessionid: str = ""

    # Anthropic API
    anthropic_api_key: str = ""

    # Notifications
    resend_api_key: str = ""
    slack_webhook_url: str = ""

    # MLflow
    mlflow_tracking_uri: str = "http://localhost:5000"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # 今日事件來源檔（pipeline 產出的忠實摘要 JSONL，一行一事件）。
    # /api/events/today 直接讀此檔（DB-optional，不查資料庫）；不存在則回 []。
    # 環境變數用 PULSE_EVENTS_FILE（也相容 EVENTS_FILE）。
    events_file: str = Field(
        default="data/events_today.jsonl",
        validation_alias=AliasChoices("PULSE_EVENTS_FILE", "EVENTS_FILE"),
    )

    # ---- 啟用某功能所需金鑰的延遲驗證（lazy / at-use）----
    # 設計取捨：所有金鑰皆為選配，缺值時不該讓整個 app 啟動失敗（多數來源/通知是 best-effort）。
    # 改採「用到才驗」：呼叫端在真正要用某功能前呼叫對應 require_*()，缺值即 fail fast 給清楚訊息。
    def require_reddit(self) -> tuple[str, str]:
        """取得 Reddit API 憑證；缺任一即報錯（給 Reddit 爬蟲用）。"""
        if not self.reddit_client_id or not self.reddit_client_secret:
            raise RuntimeError(
                "Reddit 爬蟲需要 REDDIT_CLIENT_ID 與 REDDIT_CLIENT_SECRET，"
                "請於 .env 設定後再啟用 Reddit 來源。"
            )
        return self.reddit_client_id, self.reddit_client_secret

    def require_threads(self) -> str:
        """取得 Threads sessionid；缺則報錯（給需登入的 Threads 爬蟲用）。"""
        if not self.threads_sessionid:
            raise RuntimeError(
                "Threads 登入爬蟲需要 THREADS_SESSIONID，請於 .env 設定後再啟用。"
            )
        return self.threads_sessionid

    def require_anthropic(self) -> str:
        """取得 Anthropic API key；缺則報錯（給 decide 的 LLM 合成層用）。"""
        if not self.anthropic_api_key:
            raise RuntimeError(
                "此功能需要 ANTHROPIC_API_KEY；未設定時請改用資料驅動的模板輸出。"
            )
        return self.anthropic_api_key

    def require_slack(self) -> str:
        """取得 Slack webhook URL；缺則報錯（給告警通知用）。"""
        if not self.slack_webhook_url:
            raise RuntimeError("Slack 通知需要 SLACK_WEBHOOK_URL，請於 .env 設定後再啟用。")
        return self.slack_webhook_url


settings = Settings()
