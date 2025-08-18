import sys
import os
import pytest
from httpx import AsyncClient, ASGITransport

# Add the project root to the sys.path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app

@pytest.mark.asyncio
async def test_read_root():
    # Use the explicit ASGITransport to test the app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the Bookstore API!"}
