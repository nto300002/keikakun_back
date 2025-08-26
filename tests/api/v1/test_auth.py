# tests/api/v1/test_auth.py

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app  # appをインポート
from app.models.staff import Staff
from app.core.security import verify_password

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


# --- Issue #3: サービス責任者(Admin)のサインアップAPIのテスト ---

import uuid
from app.models.enums import StaffRole


async def test_register_admin_success(async_client: AsyncClient):
    """正常系: 有効なデータでサービス責任者として正常に登録できることをテスト (APIレイヤーのモックテスト)"""
    # Arrange: テスト用のデータを準備
    payload = {
        "name": "テスト管理者",
        "email": "admin@example.com",
        "password": "a-very-secure-password",
    }

    # --- モッキング ---
    # 1. 偽の戻り値を定義
    fake_created_user = {
        "id": uuid.uuid4(),
        "name": payload["name"],
        "email": payload["email"],
        "role": StaffRole.service_administrator,
    }

    # 2. 偽のCRUDオブジェクトを定義
    class FakeCRUD:
        async def get_by_email(self, *args, **kwargs):
            return None  # ユーザーは存在しない、と答える

        async def create_admin(self, *args, **kwargs):
            return fake_created_user  # ユーザーが作成された、と答える

    # 3. DIを偽のCRUDオブジェクトで上書き
    from app.api.v1.endpoints.auths import get_staff_crud

    app.dependency_overrides[get_staff_crud] = lambda: FakeCRUD()
    # --- モッキング終了 ---

    # Act: APIエンドポイントを呼び出す
    response = await async_client.post("/api/v1/auth/register-admin", json=payload)

    # Assert: レスポンスを検証
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == payload["email"]
    assert data["name"] == payload["name"]
    assert data["role"] == "service_administrator"

    # 後片付け
    del app.dependency_overrides[get_staff_crud]

async def test_register_admin_duplicate_email(async_client: AsyncClient):
    """異常系: 重複したメールアドレスでの登録が失敗することをテスト"""
    # Arrange: ペイロードを準備。ユーザーはsetup_test_data.pyで作成済み
    payload = {
        "name": "別ユーザー",
        "email": "duplicate@example.com",  # Pre-seeded email
        "password": "password123",
    }

    # Act: 同じメールアドレスで再度登録を試みる
    response = await async_client.post("/api/v1/auth/register-admin", json=payload)

    # Assert: 409 Conflictエラーが返ることを確認
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]

@pytest.mark.parametrize(
    "payload_diff, expected_status",
    [
        ({"email": "not-an-email"}, 422),
        ({"password": None}, 422),
        ({"name": None}, 422),
    ],
)
async def test_register_admin_invalid_data(
    async_client: AsyncClient, payload_diff, expected_status
):
    """異常系: 不正な形式のデータでの登録が失敗することをテスト"""
    # Arrange: 基本のペイロードに差分をマージ
    payload = {"name": "Test", "email": "test@test.com", "password": "pass"}
    payload.update(payload_diff)
    # Noneのキーを削除
    payload = {k: v for k, v in payload.items() if v is not None}

    # Act
    response = await async_client.post("/api/v1/auth/register-admin", json=payload)

    # Assert
    assert response.status_code == expected_status


# --- Issue #4: ログインAPIとアクセストークン発行のテスト ---

async def test_login_success(async_client: AsyncClient, service_admin_user_factory):
    """正常系: 正しい認証情報でログインし、トークンが発行されることをテスト"""
    # Arrange: テストユーザーを作成
    password = "a-very-secure-password"
    user = await service_admin_user_factory(password=password)
    
    # Act: ログインAPIを呼び出す
    response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": password},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

async def test_login_failure_wrong_password(async_client: AsyncClient, service_admin_user_factory):
    """異常系: 存在するユーザーが間違ったパスワードでログインできないことをテスト"""
    # Arrange: テストユーザーを作成
    user_email = "correct.user@example.com"
    correct_password = "a-very-secure-password"
    wrong_password = "this-is-the-wrong-password"
    await service_admin_user_factory(email=user_email, password=correct_password)

    # Act: 間違ったパスワードでログインを試みる
    response = await async_client.post(
        "/api/v1/auth/token", data={"username": user_email, "password": wrong_password}
    )

    # Assert: 認証失敗(401)が返ることを確認
    assert response.status_code == 401


async def test_login_failure_user_not_found(async_client: AsyncClient):
    """異常系: 存在しないユーザーでログインできないことをテスト"""
    # Arrange: 存在しないユーザーの認証情報
    non_existent_email = "non.existent.user@example.com"
    any_password = "any-password"

    # Act: 存在しないユーザーでログインを試みる
    response = await async_client.post(
        "/api/v1/auth/token", data={"username": non_existent_email, "password": any_password}
    )

    # Assert: 認証失敗(401)が返ることを確認
    assert response.status_code == 401


# --- セキュリティ脆弱性テスト ---

async def test_security_sql_injection_on_login(async_client: AsyncClient):
    """セキュリティ: ログインフォームでのSQLインジェクションが失敗することをテスト"""
    # Arrange: SQLインジェクションペイロード
    sql_injection_payload = "' OR 1=1; --"
    
    # Act
    response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": sql_injection_payload, "password": "any-password"},
    )

    # Assert: ログインに成功せず、サーバーエラーも起きないこと
    assert response.status_code in [401, 422] # 認証失敗 or バリデーションエラー

async def test_security_xss_on_signup_and_get(
    async_client: AsyncClient
):
    """セキュリティ: 登録時のXSSペイロードが、レスポンスで無害化されることをテスト"""
    # Arrange (Part 1): XSSペイロードを含むユーザーを登録
    xss_payload = "<script>alert('XSS')</script>"
    user_payload = {
        "name": xss_payload,
        "email": "xss@example.com",
        "password": "password123",
    }
    await async_client.post("/api/v1/auth/register-admin", json=user_payload)
    
    # Arrange (Part 2): 登録したユーザーとしてログインし、トークンを取得
    login_resp = await async_client.post(
        "/api/v1/auth/token",
        data={"username": "xss@example.com", "password": "password123"},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Act: 保護されたエンドポイントから自身の情報を取得
    response = await async_client.get("/api/v1/staff/me", headers=headers)

    # Assert
    assert response.status_code == 200
    data = response.json()
    # レスポンスのnameフィールドが、スクリプトとして解釈されない文字列そのものであることを確認
    assert data["name"] == xss_payload


# --- 発展: リフレッシュトークンのテスト ---

async def test_login_returns_refresh_token(async_client: AsyncClient, service_admin_user_factory):
    """正常系: ログイン成功時にリフレッシュトークンが発行されることをテスト"""
    # Arrange: テストユーザーを作成
    password = "a-very-secure-password"
    user = await service_admin_user_factory(email="refresh-token-user@example.com", password=password)
    
    # Act: ログインAPIを呼び出す
    response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": password},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data  # This should fail
    assert data["token_type"] == "bearer"


async def test_refresh_token_success(async_client: AsyncClient, service_admin_user_factory):
    """正常系: 有効なリフレッシュトークンで新しいアクセストークンが取得できることをテスト"""
    # Arrange: ユーザーを作成し、ログインしてトークンを取得
    password = "a-very-secure-password"
    user = await service_admin_user_factory(email="refresh-success@example.com", password=password)
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": password},
    )
    # 現状は失敗するが、将来の実装を想定してrefresh_tokenを取得する
    # テストがREDの間は、ここはキーエラーになるか、ダミーの値を使う
    login_data = login_response.json()
    refresh_token = login_data.get("refresh_token", "dummy-refresh-token-for-red-test")

    # Act: 新しいアクセストークンをリクエスト
    # このエンドポイントはまだ存在しないため、404エラーになるはず
    response = await async_client.post(
        "/api/v1/auth/refresh-token",
        json={"refresh_token": refresh_token}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "refresh_token" not in data # 通常、リフレッシュ時にはアクセストークンのみ返す


async def test_refresh_token_failure_invalid_token(async_client: AsyncClient):
    """異常系: 無効なリフレッシュトークンでは新しいアクセストークンが取得できないことをテスト"""
    # Arrange: 無効なトークンを準備
    invalid_token = "this-is-not-a-valid-refresh-token"

    # Act: 無効なトークンで新しいアクセストークンをリクエスト
    # このエンドポイントはまだ存在しないため、404エラーになるはず
    response = await async_client.post(
        "/api/v1/auth/refresh-token",
        json={"refresh_token": invalid_token}
    )

    # Assert
    assert response.status_code == 401 # Unauthorized


# --- 発展: パスワードポリシーのテスト ---

@pytest.mark.parametrize(
    "password",
    [
        "short",  # 短すぎる
        "12345678",  # 数字のみ
        "abcdefgh",  # 小文字のみ
        "ABCDEFGH",  # 大文字のみ
        "!@#$%^&*",  # 記号のみ
        "abc123AB",  # 記号が含まれていない
    ],
)
async def test_register_admin_weak_password(
    async_client: AsyncClient, password: str
):
    """異常系: 弱いパスワードでのユーザー登録が失敗することをテスト"""
    # Arrange
    # Eメールが一意になるようにランダムな接尾辞を追加
    random_suffix = __import__("uuid").uuid4().hex[:6]
    payload = {
        "name": "Weak Password User",
        "email": f"weak-password-{random_suffix}@example.com",
        "password": password,
    }

    # Act
    response = await async_client.post("/api/v1/auth/register-admin", json=payload)

    # Assert
    # パスワードポリシーが実装されれば422が返るはず
    assert response.status_code == 422


# --- 発展: レートリミットのテスト ---

async def test_login_rate_limit(async_client: AsyncClient, service_admin_user_factory):
    """異常系: ログインの連続失敗でレートリミットが発動することをテスト"""
    # Arrange: テストユーザーを作成
    user_email = "rate-limit-user@example.com"
    correct_password = "a-very-secure-password"
    wrong_password = "wrong-password"
    await service_admin_user_factory(email=user_email, password=correct_password)

    # Act: 規定回数（例: 5回）まで、わざとログインを失敗させる
    # この回数は将来の実装に合わせる
    limit = 5
    for i in range(limit):
        response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": user_email, "password": wrong_password},
        )
        # 制限までは401が返ることを確認
        assert response.status_code == 401, f"Failed at attempt {i+1}"

    # Act (Final): 制限を超えた次のリクエスト
    final_response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": user_email, "password": wrong_password},
    )

    # Assert: レートリミットにより429エラーが返ることを確認
    # レートリミットが実装されるまでは401が返り、このアサーションは失敗する
    assert final_response.status_code == 429 # Too Many Requests


# --- 発展: メールアドレス確認フローのテスト ---

async def test_login_unverified_email(async_client: AsyncClient):
    """異常系: メールアドレスが未確認のユーザーはログインできないことをテスト"""
    # Arrange: 新しいユーザーを登録する
    # この時点ではメールは未確認であるべき
    random_suffix = __import__("uuid").uuid4().hex[:6]
    email = f"unverified-{random_suffix}@example.com"
    password = "a-secure-password"
    payload = {
        "name": "Unverified User",
        "email": email,
        "password": password,
    }
    # 依存関係を上書きせず、実際のDBに書き込む
    register_response = await async_client.post("/api/v1/auth/register-admin", json=payload)
    assert register_response.status_code == 201 # まず登録は成功する

    # Act: 登録したばかりのユーザーでログインを試みる
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )

    # Assert: メールが未確認のため、ログインが失敗することを確認
    # メール確認フローが実装されるまでは200が返り、このアサーションは失敗する
    assert login_response.status_code == 401 # or 403, depending on implementation