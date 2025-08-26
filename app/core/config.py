import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

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


# 設定クラスのインスタンスを作成し、他のモジュールからインポートして使用できるようにします。
settings = Settings()