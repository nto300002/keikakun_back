import sys
import os
import pytest
from httpx import AsyncClient, ASGITransport

# Add the project root to the sys.path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app

# デバッグ
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

@pytest.mark.asyncio
async def test_read_root():
    # Use the explicit ASGITransport to test the app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the Bookstore API!"}

