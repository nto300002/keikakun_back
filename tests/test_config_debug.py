import os
from urllib.parse import urlparse

def test_debug_database_url_scheme():
    """
    CI環境で実際に読み込まれているDATABASE_URLのスキーマを確認するためのテスト。
    """
    db_url = os.environ.get("DATABASE_URL")
    
    # URLがそもそも存在するかどうかをアサート
    assert db_url is not None, "Environment variable DATABASE_URL is not set!"
    
    parsed_url = urlparse(db_url)
    
    # コンソールにスキーマを出力させる
    print(f"\n[DEBUG] Detected URL scheme: {parsed_url.scheme}")
    
    # スキーマが期待通りかアサート
    assert parsed_url.scheme == "postgresql+asyncpg", \
        f"Expected scheme 'postgresql+asyncpg', but got '{parsed_url.scheme}'"