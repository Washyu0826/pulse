"""
應用設定 - 用 pydantic-settings 從環境變數載入。
"""
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

    # Anthropic API
    anthropic_api_key: str = ""

    # Notifications
    resend_api_key: str = ""
    slack_webhook_url: str = ""

    # MLflow
    mlflow_tracking_uri: str = "http://localhost:5000"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
