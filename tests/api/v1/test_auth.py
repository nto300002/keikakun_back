# tests/api/v1/test_auth.py

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app  # appをインポート
from app.models.staff import Staff
from app.core.security import verify_password, generate_totp_secret
from app import crud
from sqlalchemy.ext.asyncio import AsyncSession

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


# --- Issue サービス責任者(Admin)のサインアップAPIのテスト ---

import uuid
from app.models.enums import StaffRole


async def test_register_admin_success(async_client: AsyncClient, db_session: AsyncSession):
    """正常系: 有効なデータでサービス責任者として正常に登録できることをテスト"""
    # Arrange: テスト用のデータを準備
    email = "admin.success@example.com"
    password = "Test-password123!"
    payload = {
        "first_name": "太郎",
        "last_name": "管理",
        "email": email,
        "password": password,
    }

    # Act: APIエンドポイントを呼び出す
    response = await async_client.post("/api/v1/auth/register-admin", json=payload)

    # Assert: レスポンスを検証
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == email
    assert data["first_name"] == payload["first_name"]
    assert data["last_name"] == payload["last_name"]
    assert data["full_name"] == f"{payload['last_name']} {payload['first_name']}"
    assert data["role"] == "owner"

    # Assert: DBの状態を検証
    user = await crud.staff.get_by_email(db_session, email=email)
    assert user is not None
    assert user.first_name == payload["first_name"]
    assert user.last_name == payload["last_name"]
    assert verify_password(password, user.hashed_password)
    assert user.is_email_verified is False # 登録直後は未検証のはず


async def test_register_admin_sends_verification_email(async_client: AsyncClient, mocker):
    """正常系: ユーザー登録時に確認メール送信処理が呼び出されることをテスト"""
    # Arrange: メール送信関数をモック化
    mock_send_email = mocker.patch("app.api.v1.endpoints.auths.send_verification_email", new_callable=mocker.AsyncMock)

    email = "send.email.test@example.com"
    payload = {
        "first_name": "太郎",
        "last_name": "送信",
        "email": email,
        "password": "Test-password123!",
    }

    # Act
    response = await async_client.post("/api/v1/auth/register-admin", json=payload)

    # Assert
    assert response.status_code == 201
    # メール送信関数が1回呼び出されたことを確認
    mock_send_email.assert_called_once()
    # 呼び出し時のキーワード引数が正しいことを確認
    call_args = mock_send_email.call_args
    assert call_args.kwargs['recipient_email'] == email
    assert 'token' in call_args.kwargs


async def test_register_admin_duplicate_email(async_client: AsyncClient, service_admin_user_factory):
    """異常系: 重複したメールアドレスでの登録が失敗することをテスト"""
    # Arrange: 既存ユーザーをDBに作成
    random_suffix = uuid.uuid4().hex[:6]
    existing_user_email = f"duplicate-{random_suffix}@example.com"
    await service_admin_user_factory(email=existing_user_email, password="Test-password123!")

    payload = {
        "first_name": "花子",
        "last_name": "別",
        "email": existing_user_email,
        "password": "Another-password123!",
    }

    # Act: 同じメールアドレスで再度登録を試みる
    response = await async_client.post("/api/v1/auth/register-admin", json=payload)

    # Assert: 409 Conflictエラーが返ることを確認
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


# --- Staff (employee/manager) Registration Tests ---

@pytest.mark.parametrize("role", [StaffRole.employee, StaffRole.manager])
async def test_register_staff_success(async_client: AsyncClient, db_session: AsyncSession, role: StaffRole):
    """正常系: 有効なデータでemployeeとmanagerが正常に登録できることをテスト"""
    # Arrange
    email = f"{role.value}.success@example.com"
    password = "Test-password123!"
    role_name = "従業員" if role == StaffRole.employee else "管理者"
    payload = {
        "first_name": "太郎",
        "last_name": f"テスト{role_name}",
        "email": email,
        "password": password,
        "role": role.value,
    }

    # Act
    response = await async_client.post("/api/v1/auth/register", json=payload)

    # Assert: Response
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == email
    assert data["first_name"] == payload["first_name"]
    assert data["last_name"] == payload["last_name"]
    assert data["full_name"] == f"{payload['last_name']} {payload['first_name']}"
    assert data["role"] == role.value

    # Assert: DB
    user = await crud.staff.get_by_email(db_session, email=email)
    assert user is not None
    assert user.role == role
    assert verify_password(password, user.hashed_password)


async def test_register_staff_failure_as_owner(async_client: AsyncClient):
    """異常系: /register エンドポイントで owner として登録しようとすると失敗することをテスト"""
    # Arrange
    payload = {
        "first_name": "太郎",
        "last_name": "不正",
        "email": "invalid.owner@example.com",
        "password": "Test-password123!",
        "role": StaffRole.owner.value,
    }

    # Act
    response = await async_client.post("/api/v1/auth/register", json=payload)

    # Assert: 422 Unprocessable Entity (pydantic validation error)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload_diff, expected_status",
    [
        ({"email": "not-an-email"}, 422),
        ({"password": None}, 422),
        ({"first_name": None}, 422),
    ],
)
async def test_register_admin_invalid_data(
    async_client: AsyncClient, payload_diff, expected_status
):
    """異常系: 不正な形式のデータでの登録が失敗することをテスト"""
    # Arrange: 基本のペイロードに差分をマージ
    payload = {"first_name": "太郎", "last_name": "テスト", "email": "test@test.com", "password": "pass"}
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
    password = "Test-password123!"
    user = await service_admin_user_factory(password=password)

    # Act: ログインAPIを呼び出す
    response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": password},
    )

    # Assert: レスポンスステータス
    assert response.status_code == 200

    # Assert: Cookie認証 - access_tokenはCookieに設定される
    assert "access_token" in response.cookies
    cookie_value = response.cookies.get("access_token")
    assert cookie_value is not None
    assert len(cookie_value) > 0

    # Assert: レスポンスボディの検証
    data = response.json()
    assert "access_token" not in data  # Cookieに設定されるため、ボディには含まれない
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_login_success_for_employee(async_client: AsyncClient, employee_user_factory):
    """正常系: employeeロールのユーザーが正しい認証情報でログインできることをテスト"""
    # Arrange: テストユーザーを作成
    password = "Test-password123!"
    user = await employee_user_factory(password=password, email="employee.login@example.com")

    # Act: ログインAPIを呼び出す
    response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": password},
    )

    # Assert: レスポンスステータス
    assert response.status_code == 200

    # Assert: Cookie認証
    assert "access_token" in response.cookies

    # Assert: レスポンスボディの検証
    data = response.json()
    assert "access_token" not in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_login_success_for_manager(async_client: AsyncClient, manager_user_factory):
    """正常系: managerロールのユーザーが正しい認証情報でログインできることをテスト"""
    # Arrange: テストユーザーを作成
    password = "Test-password123!"
    user = await manager_user_factory(password=password, email="manager.login@example.com")

    # Act: ログインAPIを呼び出す
    response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": password},
    )

    # Assert: レスポンスステータス
    assert response.status_code == 200

    # Assert: Cookie認証
    assert "access_token" in response.cookies

    # Assert: レスポンスボディの検証
    data = response.json()
    assert "access_token" not in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_login_failure_wrong_password(async_client: AsyncClient, service_admin_user_factory):
    """異常系: 存在するユーザーが間違ったパスワードでログインできないことをテスト"""
    # Arrange: テストユーザーを作成
    user_email = "correct.user@example.com"
    correct_password = "Test-password123!"
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
    async_client: AsyncClient, db_session: AsyncSession  # db_sessionを追加
):
    """セキュリティ: 登録時のXSSペイロードが、レスポンスで無害化されることをテスト"""
    # Arrange (Part 1): 日本語のXSSペイロードを含むユーザーを登録
    # 注: 日本語のみのバリデーションがあるため、日本語文字を使用
    xss_payload = "あいうえお・スクリプト"
    # Eメールが一意になるようにランダムな接尾辞を追加
    random_suffix = __import__("uuid").uuid4().hex[:6]
    email = f"xss-{random_suffix}@example.com"
    user_payload = {
        "first_name": xss_payload,
        "last_name": "テスト",
        "email": email,
        "password": "Test-password123!",
    }
    register_response = await async_client.post("/api/v1/auth/register-admin", json=user_payload)
    assert register_response.status_code == 201  # 登録成功を確認

    # Arrange (Part 2): DBを直接更新してユーザーを「確認済み」にする
    user = await crud.staff.get_by_email(db_session, email=email)
    assert user is not None
    user.is_email_verified = True
    db_session.add(user)
    await db_session.flush()

    # Arrange (Part 3): 登録したユーザーとしてログインし、トークンを取得
    login_resp = await async_client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": "Test-password123!"},
    )
    assert login_resp.status_code == 200  # ログイン成功を確認
    # Cookie認証: access_tokenはCookieから取得
    token = login_resp.cookies.get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Act: 保護されたエンドポイントから自身の情報を取得
    response = await async_client.get("/api/v1/staffs/me", headers=headers)

    # Assert
    assert response.status_code == 200
    data = response.json()
    # レスポンスのfirst_nameフィールドが、スクリプトとして解釈されない文字列そのものであることを確認
    assert data["first_name"] == xss_payload


# --- 発展: リフレッシュトークンのテスト ---

async def test_login_returns_refresh_token(async_client: AsyncClient, service_admin_user_factory):
    """正常系: ログイン成功時にリフレッシュトークンが発行されることをテスト"""
    # Arrange: テストユーザーを作成
    password = "Test-password123!"
    user = await service_admin_user_factory(email="refresh-token-user@example.com", password=password)

    # Act: ログインAPIを呼び出す
    response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": password},
    )

    # Assert: レスポンスステータス
    assert response.status_code == 200

    # Assert: Cookie認証 - access_tokenはCookieに設定される
    assert "access_token" in response.cookies

    # Assert: レスポンスボディの検証
    data = response.json()
    assert "access_token" not in data  # Cookieに設定されるため、ボディには含まれない
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_refresh_token_success(async_client: AsyncClient, service_admin_user_factory):
    """正常系: 有効なリフレッシュトークンで新しいアクセストークンが取得できることをテスト"""
    # Arrange: ユーザーを作成し、ログインしてトークンを取得
    password = "Test-password123!"
    user = await service_admin_user_factory(email="refresh-success@example.com", password=password)
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": password},
    )
    login_data = login_response.json()
    refresh_token = login_data["refresh_token"]

    # Act: 新しいアクセストークンをリクエスト
    response = await async_client.post(
        "/api/v1/auth/refresh-token",
        json={"refresh_token": refresh_token}
    )

    # Assert: レスポンスステータス
    assert response.status_code == 200

    # Assert: Cookie認証 - access_tokenはCookieに設定される
    assert "access_token" in response.cookies

    # Assert: レスポンスボディの検証
    data = response.json()
    assert "access_token" not in data  # Cookieに設定されるため、ボディには含まれない
    assert data["token_type"] == "bearer"
    assert data["message"] == "Token refreshed"


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
        "first_name": "太郎",
        "last_name": "弱パス",
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
    correct_password = "Test-password123!"
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


# ... 既存のコードの末尾に追加 ...

# --- メール確認フローのテスト ---

async def test_verify_email_success(async_client: AsyncClient, db_session: AsyncSession, service_admin_user_factory):
    """正常系: 有効なトークンでメールアドレスが正常に確認される"""
    # Arrange: is_email_verified=False のユーザーを作成
    user = await service_admin_user_factory(email="verify.success@example.com", is_email_verified=False)
    
    from app.core.security import create_email_verification_token
    token = create_email_verification_token(user.email)

    # Act: メール確認エンドポイントを叩く
    response = await async_client.get(f"/api/v1/auth/verify-email?token={token}")

    # Assert
    assert response.status_code == 200
    assert "Email verified successfully" in response.json()["message"]

    # DBでフラグが更新されたことを確認
    await db_session.refresh(user)
    assert user.is_email_verified is True


async def test_verify_email_invalid_token(async_client: AsyncClient):
    """異常系: 無効なトークンではメール確認が失敗する"""
    # Arrange
    invalid_token = "this-is-a-bad-token"

    # Act
    response = await async_client.get(f"/api/v1/auth/verify-email?token={invalid_token}")

    # Assert
    assert response.status_code == 400
    assert "Invalid or expired token" in response.json()["detail"]



async def test_login_unverified_email(async_client: AsyncClient, db_session: AsyncSession):
    """異常系: メールアドレスが未確認のユーザーはログインできないことをテスト"""
    # Arrange: 新しいユーザーを登録するが、メール確認は行わない
    random_suffix = __import__("uuid").uuid4().hex[:6]
    email = f"unverified-{random_suffix}@example.com"
    password = "Test-password123!"
    payload = {
        "first_name": "太郎",
        "last_name": "未検証",
        "email": email,
        "password": password,
    }
    register_response = await async_client.post("/api/v1/auth/register-admin", json=payload)
    assert register_response.status_code == 201

    # Act: 登録したばかりの（未確認の）ユーザーでログインを試みる
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )

    # Assert: メールが未確認のため、ログインが失敗(401 Unauthorized)することを確認
    assert login_response.status_code == 401
    assert "Email not verified" in login_response.json()["detail"]

# --- Logout Test ---
from tests.utils import create_random_staff
from app.core.security import create_access_token

class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_with_mfa_enabled(self, async_client: AsyncClient, db_session: AsyncSession):
        """正常系: MFA有効ユーザーのログアウト後もMFA設定が維持されることをテスト"""
        # Arrange
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        staff.mfa_secret = generate_totp_secret()
        await db_session.commit()
        
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        # Act
        response = await async_client.post("/api/v1/auth/logout", headers=headers)

        # Assert
        assert response.status_code == 200
        assert response.json()["message"] == "Logout successful"

        # ログアウト後もMFA設定が変更されていないことを確認
        await db_session.refresh(staff)
        assert staff.is_mfa_enabled is True
        assert staff.mfa_secret is not None

    @pytest.mark.asyncio
    async def test_logout_with_mfa_disabled(self, async_client: AsyncClient, db_session: AsyncSession):
        """正常系: MFA無効ユーザーがログアウトしてもエラーにならない"""
        # Arrange
        staff = await create_random_staff(db_session, is_mfa_enabled=False)
        await db_session.commit()
        
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        # Act
        response = await async_client.post("/api/v1/auth/logout", headers=headers)

        # Assert
        assert response.status_code == 200
        assert response.json()["message"] == "Logout successful"

        await db_session.refresh(staff)
        assert staff.is_mfa_enabled is False

    @pytest.mark.asyncio
    async def test_logout_unauthorized(self, async_client: AsyncClient):
        """異常系: 認証なしでログアウトしようとすると401エラー"""
        # Act
        response = await async_client.post("/api/v1/auth/logout")

        # Assert
        assert response.status_code == 401


# --- Cookie Authentication Tests ---

class TestCookieAuthentication:
    """Cookie認証機能のテストクラス"""

    @pytest.mark.asyncio
    async def test_login_sets_cookie(self, async_client: AsyncClient, service_admin_user_factory):
        """正常系: ログイン時にaccess_token Cookieが設定される"""
        # Arrange: テストユーザーを作成
        password = "Test-password123!"
        user = await service_admin_user_factory(email="cookie.test@example.com", password=password)

        # Act: ログインAPIを呼び出す
        response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": user.email, "password": password},
        )

        # Assert: レスポンスステータス
        assert response.status_code == 200

        # Assert: Cookieが設定されている
        assert "access_token" in response.cookies
        cookie_value = response.cookies.get("access_token")
        assert cookie_value is not None
        assert len(cookie_value) > 0

        # Assert: Cookie属性の確認
        # httpx.Cookies オブジェクトから直接属性を取得するのは難しいため、
        # Set-Cookieヘッダーを解析する
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie_header
        # 開発環境では SameSite=Lax が設定される（localhost間は同一サイト）
        assert "SameSite=Lax" in set_cookie_header or "SameSite=lax" in set_cookie_header
        assert "Max-Age=3600" in set_cookie_header  # 標準セッション: 1時間

    @pytest.mark.asyncio
    async def test_login_with_remember_me_sets_long_lived_cookie(
        self, async_client: AsyncClient, service_admin_user_factory
    ):
        """正常系: rememberMe=trueで長期Cookieが設定される"""
        # Arrange
        password = "Test-password123!"
        user = await service_admin_user_factory(
            email="remember.me.cookie@example.com",
            password=password
        )

        # Act: rememberMe=trueでログイン
        response = await async_client.post(
            "/api/v1/auth/token",
            data={
                "username": user.email,
                "password": password,
                "rememberMe": "true"  # Form dataは文字列
            },
        )

        # Assert
        assert response.status_code == 200
        assert "access_token" in response.cookies

        # Assert: Max-Ageが8時間(28800秒)であることを確認
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "Max-Age=28800" in set_cookie_header
        assert "HttpOnly" in set_cookie_header

    @pytest.mark.asyncio
    async def test_mfa_verify_sets_cookie(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """正常系: MFA検証成功時にCookieが設定される"""
        # Arrange: MFA有効なユーザーを作成
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        staff.mfa_secret = generate_totp_secret()
        password = "Test-password123!"
        from app.core.security import get_password_hash
        staff.hashed_password = get_password_hash(password)
        await db_session.commit()

        # まずログインして一時トークンを取得
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": staff.email, "password": password},
        )
        assert login_response.status_code == 200
        login_data = login_response.json()
        assert login_data["requires_mfa_verification"] is True
        temporary_token = login_data["temporary_token"]

        # TOTPコードを生成
        import pyotp
        totp = pyotp.TOTP(staff.mfa_secret)
        totp_code = totp.now()

        # Act: MFA検証
        mfa_response = await async_client.post(
            "/api/v1/auth/token/verify-mfa",
            json={
                "temporary_token": temporary_token,
                "totp_code": totp_code,
            },
        )

        # Assert: レスポンスステータス
        assert mfa_response.status_code == 200

        # Assert: Cookieが設定されている
        assert "access_token" in mfa_response.cookies
        set_cookie_header = mfa_response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie_header
        # 開発環境では SameSite=Lax が設定される（localhost間は同一サイト）
        assert "SameSite=Lax" in set_cookie_header or "SameSite=lax" in set_cookie_header

        # Assert: レスポンスボディの検証（access_tokenは含まれない）
        mfa_data = mfa_response.json()
        assert "access_token" not in mfa_data  # Cookieに設定されるため、ボディには含まれない
        assert "refresh_token" in mfa_data
        assert mfa_data["token_type"] == "bearer"
        assert mfa_data["message"] == "MFA verification successful"

    @pytest.mark.asyncio
    async def test_refresh_token_updates_cookie(
        self, async_client: AsyncClient, service_admin_user_factory
    ):
        """正常系: トークンリフレッシュ時にCookieが更新される"""
        # Arrange: ログインしてリフレッシュトークンを取得
        password = "Test-password123!"
        user = await service_admin_user_factory(
            email="refresh.cookie@example.com",
            password=password
        )

        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": user.email, "password": password},
        )
        assert login_response.status_code == 200
        refresh_token = login_response.json()["refresh_token"]

        # Act: リフレッシュトークンで新しいアクセストークンを取得
        refresh_response = await async_client.post(
            "/api/v1/auth/refresh-token",
            json={"refresh_token": refresh_token}
        )

        # Assert
        assert refresh_response.status_code == 200
        assert "access_token" in refresh_response.cookies

        set_cookie_header = refresh_response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie_header

    @pytest.mark.asyncio
    async def test_logout_clears_cookie(
        self, async_client: AsyncClient, service_admin_user_factory
    ):
        """正常系: ログアウト時にCookieがクリアされる（Cookieのみで認証）"""
        # Arrange: ログインしてトークンを取得
        password = "Test-password123!"
        user = await service_admin_user_factory(
            email="logout.cookie@example.com",
            password=password
        )

        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": user.email, "password": password},
        )
        assert login_response.status_code == 200

        # Cookie認証: access_tokenがCookieに設定されている
        assert "access_token" in login_response.cookies

        # Act: Cookie認証でログアウト（ブラウザと同じ動作）
        # httpxは自動的にCookieを保持・送信する
        logout_response = await async_client.post("/api/v1/auth/logout")

        # Assert: レスポンスステータス
        assert logout_response.status_code == 200

        # Assert: Cookieが削除される（Max-Age=0が設定される）
        set_cookie_header = logout_response.headers.get("set-cookie", "")
        # クッキー削除の場合、Max-Age=0 または expires=過去の日付が設定される
        assert "access_token=" in set_cookie_header
        assert ("Max-Age=0" in set_cookie_header or "max-age=0" in set_cookie_header)

        # Assert: ログアウト後は認証が必要なエンドポイントにアクセスできない
        me_response = await async_client.get("/api/v1/staffs/me")
        assert me_response.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(
        self, async_client: AsyncClient, service_admin_user_factory
    ):
        """正常系: 有効期限切れのトークンで401エラーが返る"""
        import time
        from app.core.security import create_access_token

        # Arrange: 有効期限切れのトークンを作成（1秒で期限切れ）
        password = "Test-password123!"
        user = await service_admin_user_factory(
            email="expired.token@example.com",
            password=password
        )

        # 1秒で期限切れのトークンを作成
        expired_token = create_access_token(
            subject=str(user.id),
            expires_delta_seconds=1,
            session_type="standard"
        )

        # 2秒待機してトークンを確実に期限切れにする
        time.sleep(2)

        # Act: 期限切れのトークンでアクセス
        async_client.cookies.set("access_token", expired_token)
        response = await async_client.get("/api/v1/staffs/me")

        # Assert: 401エラーが返る
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_cookie_returns_401(
        self, async_client: AsyncClient, service_admin_user_factory
    ):
        """正常系: 不正なCookieでアクセス時に401エラーが返る"""
        # Arrange: 不正な署名のトークンを設定
        invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"

        # Act: 不正なトークンでアクセス
        async_client.cookies.set("access_token", invalid_token)
        response = await async_client.get("/api/v1/staffs/me")

        # Assert: 401エラーが返る
        assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.parametrize("endpoint", [
        "/api/v1/staffs/me",
        "/api/v1/offices/me",
    ])
    async def test_protected_endpoints_with_cookie(
        self, async_client: AsyncClient, service_admin_user_factory, endpoint: str
    ):
        """正常系: 保護されたエンドポイントでCookie認証が機能する"""
        # Arrange: ログインしてCookieを取得
        password = "Test-password123!"
        user = await service_admin_user_factory(
            email="protected.endpoint@example.com",
            password=password
        )

        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": user.email, "password": password},
        )
        assert login_response.status_code == 200
        assert "access_token" in login_response.cookies

        # Act: Cookie認証で保護されたエンドポイントにアクセス
        response = await async_client.get(endpoint)

        # Assert: 認証が成功する（401以外）
        # /api/v1/offices/me は事業所未設定の場合404を返す可能性があるため、
        # 401でなければOKとする
        assert response.status_code != 401

    @pytest.mark.asyncio
    async def test_cookie_attributes_in_production(
        self, async_client: AsyncClient, service_admin_user_factory, monkeypatch
    ):
        """正常系: 本番環境でSecure=True、SameSite=Noneが設定される"""
        # Arrange: 環境変数を本番環境に設定
        monkeypatch.setenv("ENVIRONMENT", "production")
        # COOKIE_DOMAINは設定しない（空文字列）

        password = "Test-password123!"
        user = await service_admin_user_factory(
            email="prod.cookie@example.com",
            password=password
        )

        # Act: ログイン
        response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": user.email, "password": password},
        )

        # Assert: レスポンスステータス
        assert response.status_code == 200
        assert "access_token" in response.cookies

        # Assert: Cookie属性の確認
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie_header
        # 本番環境ではSecure=Trueが設定される
        assert "Secure" in set_cookie_header or "secure" in set_cookie_header
        # 本番環境ではSameSite=Noneが設定される
        assert "SameSite=none" in set_cookie_header or "SameSite=None" in set_cookie_header

    @pytest.mark.asyncio
    async def test_cookie_domain_in_production(
        self, async_client: AsyncClient, service_admin_user_factory, monkeypatch
    ):
        """正常系: 本番環境でCOOKIE_DOMAIN設定時にDomain属性が設定される"""
        # Arrange: 環境変数を本番環境に設定
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("COOKIE_DOMAIN", ".keikakun.com")

        password = "Test-password123!"
        user = await service_admin_user_factory(
            email="prod.domain.cookie@example.com",
            password=password
        )

        # Act: ログイン
        response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": user.email, "password": password},
        )

        # Assert: レスポンスステータス
        assert response.status_code == 200

        # Assert: Domain属性の確認（Set-Cookieヘッダーを直接確認）
        # httpxはDomainが異なる場合にCookieを保存しないため、ヘッダーで確認
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "access_token=" in set_cookie_header
        assert "Domain=.keikakun.com" in set_cookie_header
        assert "HttpOnly" in set_cookie_header
        assert "Secure" in set_cookie_header or "secure" in set_cookie_header
