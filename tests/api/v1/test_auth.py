# tests/api/v1/test_auth.py

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app  # appをインポート
from app.models.staff import Staff
from app.core.security import verify_password
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
        "name": "テスト管理者",
        "email": email,
        "password": password,
    }

    # Act: APIエンドポイントを呼び出す
    response = await async_client.post("/api/v1/auth/register-admin", json=payload)

    # Assert: レスポンスを検証
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == email
    assert data["name"] == payload["name"]
    assert data["role"] == "owner"

    # Assert: DBの状態を検証
    user = await crud.staff.get_by_email(db_session, email=email)
    assert user is not None
    assert user.name == payload["name"]
    assert verify_password(password, user.hashed_password)
    assert user.is_email_verified is False # 登録直後は未検証のはず


async def test_register_admin_sends_verification_email(async_client: AsyncClient, mocker):
    """正常系: ユーザー登録時に確認メール送信処理が呼び出されることをテスト"""
    # Arrange: メール送信関数をモック化
    mock_send_email = mocker.patch("app.api.v1.endpoints.auths.send_verification_email", new_callable=mocker.AsyncMock)
    
    email = "send.email.test@example.com"
    payload = {
        "name": "メール送信テスト",
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
        "name": "別ユーザー",
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
    payload = {
        "name": f"テスト{role.value}",
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
    assert data["name"] == payload["name"]
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
        "name": "不正なオーナー",
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
    password = "Test-password123!"
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

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
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

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
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
    # Arrange (Part 1): XSSペイロードを含むユーザーを登録
    xss_payload = "<script>alert('XSS')</script>"
    # Eメールが一意になるようにランダムな接尾辞を追加
    random_suffix = __import__("uuid").uuid4().hex[:6]
    email = f"xss-{random_suffix}@example.com"
    user_payload = {
        "name": xss_payload,
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
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Act: 保護されたエンドポイントから自身の情報を取得
    response = await async_client.get("/api/v1/staffs/me", headers=headers)

    # Assert
    assert response.status_code == 200
    data = response.json()
    # レスポンスのnameフィールドが、スクリプトとして解釈されない文字列そのものであることを確認
    assert data["name"] == xss_payload


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

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data  # This should fail
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
        "name": "Unverified User",
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