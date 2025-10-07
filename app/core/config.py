import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pydantic import SecretStr

ENV_FILE = os.getenv("ENV_FILE", ".env")

class Settings(BaseSettings):
    """
    アプリケーションの設定を管理するクラス。
    .envファイルから環境変数を読み込みます。
    """
    # .envファイルを読み込むための設定
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding='utf-8', extra='ignore'
    )

    # --- JWT設定 ---
    # `openssl rand -hex 32` コマンドなどで生成した強力な秘密鍵を設定してください。
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    # アクセストークンの有効期限（分単位）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7日間

    # --- データベースURL ---
    # Alembicやアプリケーション本体が使用する本番/開発用DBのURL
    DATABASE_URL: str

    # --- メール設定 ---
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[SecretStr] = None
    MAIL_FROM: Optional[str] = None
    MAIL_PORT: int = 587
    MAIL_SERVER: Optional[str] = None
    MAIL_STARTTLS: bool = False
    MAIL_SSL_TLS: bool = False
    MAIL_DEBUG: int = 1  # 0=False, 1=True

    # --- API設定 ---
    API_V1_STR: str = "/api/v1"

    # --- フロントエンド設定 ---
    FRONTEND_URL: str

    # --- S3 Storage Settings ---
    S3_ENDPOINT_URL: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[SecretStr] = None
    S3_BUCKET_NAME: Optional[str] = None
    S3_REGION: Optional[str] = None


# 設定クラスのインスタンスを作成し、他のモジュールからインポートして使用できるようにします。
settings = Settings()