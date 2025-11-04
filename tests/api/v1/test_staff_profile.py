"""スタッフプロフィール編集機能のテスト"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.staff import Staff

pytestmark = pytest.mark.asyncio


# --- 名前変更機能のテスト ---

@pytest_asyncio.fixture
async def test_staff_user(service_admin_user_factory):
    """テスト用スタッフユーザーを作成"""
    return await service_admin_user_factory(
        email="staff@example.com",
        name="Test Staff"
    )


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_update_staff_name_success(
    async_client: AsyncClient,
    mock_current_user: Staff,
    db_session: AsyncSession
):
    """正常系: スタッフが自分の名前を正しく変更できる"""
    # Arrange
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "last_name": "山田",
        "first_name": "太郎",
        "last_name_furigana": "やまだ",
        "first_name_furigana": "たろう"
    }

    # Act
    response = await async_client.patch(
        "/api/v1/staffs/me/name",
        json=payload,
        headers=headers
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["last_name"] == "山田"
    assert data["first_name"] == "太郎"
    assert data["full_name"] == "山田 太郎"
    assert data["last_name_furigana"] == "やまだ"
    assert data["first_name_furigana"] == "たろう"
    assert "updated_at" in data


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_update_staff_name_trim_whitespace(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """正常系: 前後の空白が自動でトリミングされる"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "last_name": "  山田  ",
        "first_name": "  太郎  ",
        "last_name_furigana": "  やまだ  ",
        "first_name_furigana": "  たろう  "
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/name",
        json=payload,
        headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["last_name"] == "山田"
    assert data["first_name"] == "太郎"
    assert data["last_name_furigana"] == "やまだ"
    assert data["first_name_furigana"] == "たろう"


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_update_staff_name_normalize_spaces(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """正常系: 連続する空白が1つのスペースに正規化される"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "last_name": "山  田",
        "first_name": "太  郎",
        "last_name_furigana": "や  ま  だ",
        "first_name_furigana": "た  ろう"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/name",
        json=payload,
        headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["last_name"] == "山 田"
    assert data["first_name"] == "太 郎"
    assert data["last_name_furigana"] == "や ま だ"
    assert data["first_name_furigana"] == "た ろう"


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_update_staff_name_validation_empty(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 空の名前は拒否される"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "last_name": "",
        "first_name": "太郎",
        "last_name_furigana": "やまだ",
        "first_name_furigana": "たろう"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/name",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "名前は必須です" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_update_staff_name_validation_too_long(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 長すぎる名前は拒否される"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "last_name": "あ" * 51,  # 51文字
        "first_name": "太郎",
        "last_name_furigana": "やまだ",
        "first_name_furigana": "たろう"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/name",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "50文字以内" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_update_staff_name_validation_invalid_chars_in_name(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 名前に半角英数字が含まれる場合は拒否される"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "last_name": "Yamada123",
        "first_name": "太郎",
        "last_name_furigana": "やまだ",
        "first_name_furigana": "たろう"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/name",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "使用できない文字" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_update_staff_name_validation_furigana_not_hiragana(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: ふりがなにカタカナや漢字が含まれる場合は拒否される"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "last_name": "山田",
        "first_name": "太郎",
        "last_name_furigana": "ヤマダ",  # カタカナ
        "first_name_furigana": "たろう"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/name",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "ひらがなで入力" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_update_staff_name_validation_numbers_only(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 数字のみの名前は拒否される"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "last_name": "123",
        "first_name": "456",
        "last_name_furigana": "やまだ",
        "first_name_furigana": "たろう"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/name",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "数字のみは使用できません" in response.text


async def test_update_staff_name_no_auth(async_client: AsyncClient):
    """異常系: 認証なしではアクセスできない"""
    payload = {
        "last_name": "山田",
        "first_name": "太郎",
        "last_name_furigana": "やまだ",
        "first_name_furigana": "たろう"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/name",
        json=payload
    )

    assert response.status_code == 401


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_update_staff_name_with_special_chars(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """正常系: 許可された記号（・、々）を含む名前"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "last_name": "佐々木",
        "first_name": "太郎",
        "last_name_furigana": "ささき",
        "first_name_furigana": "たろう"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/name",
        json=payload,
        headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["last_name"] == "佐々木"


# --- パスワード変更機能のテスト ---

@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_change_password_success(
    async_client: AsyncClient,
    mock_current_user: Staff,
    db_session: AsyncSession
):
    """正常系: パスワードを正しく変更できる"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "current_password": "a-very-secure-password",
        "new_password": "NewSecure123!",
        "new_password_confirm": "NewSecure123!"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/password",
        json=payload,
        headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "パスワードを変更しました"
    assert "updated_at" in data


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_change_password_wrong_current(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 現在のパスワードが間違っている"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "current_password": "wrong-password",
        "new_password": "NewSecure123!",
        "new_password_confirm": "NewSecure123!"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/password",
        json=payload,
        headers=headers
    )

    assert response.status_code == 400
    assert "現在のパスワードが正しくありません" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_change_password_mismatch(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 新しいパスワードが一致しない"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "current_password": "a-very-secure-password",
        "new_password": "NewSecure123!",
        "new_password_confirm": "DifferentPass123!"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/password",
        json=payload,
        headers=headers
    )

    assert response.status_code == 400
    assert "一致しません" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_change_password_too_short(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: パスワードが短すぎる"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "current_password": "a-very-secure-password",
        "new_password": "Short1!",
        "new_password_confirm": "Short1!"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/password",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "8文字以上" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_change_password_no_uppercase(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 大文字が含まれていない"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "current_password": "a-very-secure-password",
        "new_password": "newsecure123!",
        "new_password_confirm": "newsecure123!"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/password",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "大文字" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_change_password_no_lowercase(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 小文字が含まれていない"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "current_password": "a-very-secure-password",
        "new_password": "NEWSECURE123!",
        "new_password_confirm": "NEWSECURE123!"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/password",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "小文字" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_change_password_no_digit(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 数字が含まれていない"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "current_password": "a-very-secure-password",
        "new_password": "NewSecurePass!",
        "new_password_confirm": "NewSecurePass!"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/password",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "数字" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_change_password_no_special_char(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 特殊文字が含まれていない"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "current_password": "a-very-secure-password",
        "new_password": "NewSecure123",
        "new_password_confirm": "NewSecure123"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/password",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "特殊文字" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_change_password_repeated_chars(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 同じ文字が3回以上連続している"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "current_password": "a-very-secure-password",
        "new_password": "Newaaa123!",
        "new_password_confirm": "Newaaa123!"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/password",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "連続して使用できません" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_change_password_common_password(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: 一般的なパスワードは拒否される"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "current_password": "a-very-secure-password",
        "new_password": "Password123!",
        "new_password_confirm": "Password123!"
    }

    response = await async_client.patch(
        "/api/v1/staffs/me/password",
        json=payload,
        headers=headers
    )

    assert response.status_code == 422
    assert "一般的すぎる" in response.text


# --- メールアドレス変更機能のテスト ---

@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_request_email_change_success(
    async_client: AsyncClient,
    mock_current_user: Staff,
    db_session: AsyncSession
):
    """正常系: メールアドレス変更リクエストが成功する"""
    from unittest.mock import patch

    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "new_email": "newemail@example.com",
        "password": "a-very-secure-password"
    }

    # メール送信をモック
    with patch('app.core.mail.send_email_change_verification') as mock_verification, \
         patch('app.core.mail.send_email_change_notification') as mock_notification:

        response = await async_client.post(
            "/api/v1/staffs/me/email",
            json=payload,
            headers=headers
        )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert "確認メールを送信しました" in data["message"]
    assert "verification_token_expires_at" in data

    # メール送信が呼ばれたことを確認
    mock_verification.assert_called_once()
    mock_notification.assert_called_once()


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_request_email_change_wrong_password(
    async_client: AsyncClient,
    mock_current_user: Staff
):
    """異常系: パスワードが間違っている場合エラーになる"""
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "new_email": "newemail@example.com",
        "password": "wrong-password"
    }

    response = await async_client.post(
        "/api/v1/staffs/me/email",
        json=payload,
        headers=headers
    )

    assert response.status_code == 400
    assert "パスワードが正しくありません" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_request_email_change_duplicate_email(
    async_client: AsyncClient,
    mock_current_user: Staff,
    service_admin_user_factory
):
    """異常系: 既に使用されているメールアドレスは使用できない"""
    from unittest.mock import patch

    # 別のユーザーを作成
    await service_admin_user_factory(
        email="existing@example.com",
        name="Existing User"
    )

    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "new_email": "existing@example.com",
        "password": "a-very-secure-password"
    }

    response = await async_client.post(
        "/api/v1/staffs/me/email",
        json=payload,
        headers=headers
    )

    assert response.status_code == 400
    assert "既に使用されています" in response.text


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_request_email_change_rate_limit(
    async_client: AsyncClient,
    mock_current_user: Staff,
    db_session: AsyncSession
):
    """異常系: レート制限（24時間以内に3回まで）"""
    from unittest.mock import patch
    from datetime import datetime, timedelta
    from app.models.staff_profile import EmailChangeRequest as EmailChangeRequestModel

    headers = {"Authorization": "Bearer fake-token"}

    # 24時間以内に3回のリクエストを作成
    for i in range(3):
        email_request = EmailChangeRequestModel(
            staff_id=str(mock_current_user.id),
            old_email=mock_current_user.email,
            new_email=f"test{i}@example.com",
            verification_token=f"token-{i}",
            expires_at=datetime.utcnow() + timedelta(minutes=30),
            status="pending",
            created_at=datetime.utcnow() - timedelta(hours=i)
        )
        db_session.add(email_request)

    await db_session.flush()

    # 4回目のリクエストを試みる（レート制限超過）
    payload = {
        "new_email": "fourth@example.com",
        "password": "a-very-secure-password"
    }

    response = await async_client.post(
        "/api/v1/staffs/me/email",
        json=payload,
        headers=headers
    )

    assert response.status_code == 429
    assert "24時間後に再度お試しください" in response.text


async def test_request_email_change_no_auth(
    async_client: AsyncClient
):
    """異常系: 未認証ユーザーはアクセスできない"""
    payload = {
        "new_email": "newemail@example.com",
        "password": "a-very-secure-password"
    }

    response = await async_client.post(
        "/api/v1/staffs/me/email",
        json=payload
    )

    assert response.status_code == 401


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_verify_email_change_success(
    async_client: AsyncClient,
    mock_current_user: Staff,
    db_session: AsyncSession
):
    """正常系: 確認トークンでメールアドレス変更が完了する"""
    from unittest.mock import patch
    from datetime import datetime, timedelta, timezone
    from app.models.staff_profile import EmailChangeRequest as EmailChangeRequestModel

    # メールアドレス変更リクエストを作成
    email_request = EmailChangeRequestModel(
        staff_id=str(mock_current_user.id),
        old_email=mock_current_user.email,
        new_email="verified@example.com",
        verification_token="valid-token-123",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        status="pending"
    )
    db_session.add(email_request)
    await db_session.flush()

    payload = {
        "verification_token": "valid-token-123"
    }

    # メール送信をモック
    with patch('app.core.mail.send_email_change_completed') as mock_completed:
        response = await async_client.post(
            "/api/v1/staffs/me/email/verify",
            json=payload
        )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "メールアドレスを変更しました"
    assert data["new_email"] == "verified@example.com"

    # 完了メールが送信されたことを確認
    mock_completed.assert_called_once()


async def test_verify_email_change_invalid_token(
    async_client: AsyncClient
):
    """異常系: 無効なトークンはエラーになる"""
    payload = {
        "verification_token": "invalid-token"
    }

    response = await async_client.post(
        "/api/v1/staffs/me/email/verify",
        json=payload
    )

    assert response.status_code == 400
    assert "無効な確認トークンです" in response.text


async def test_verify_email_change_expired_token(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_staff_user
):
    """異常系: 有効期限切れのトークンはエラーになる"""
    from datetime import datetime, timedelta, timezone
    from app.models.staff_profile import EmailChangeRequest as EmailChangeRequestModel

    # 期限切れのリクエストを作成
    email_request = EmailChangeRequestModel(
        staff_id=str(test_staff_user.id),
        old_email=test_staff_user.email,
        new_email="expired@example.com",
        verification_token="expired-token-123",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # 既に期限切れ
        status="pending"
    )
    db_session.add(email_request)
    await db_session.flush()

    payload = {
        "verification_token": "expired-token-123"
    }

    response = await async_client.post(
        "/api/v1/staffs/me/email/verify",
        json=payload
    )

    assert response.status_code == 400
    assert "有効期限が切れています" in response.text


# --- MissingGreenletエラー検証テスト ---

@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_update_staff_name_no_missing_greenlet_error(
    async_client: AsyncClient,
    mock_current_user: Staff,
    db_session: AsyncSession
):
    """
    テストケース64: セッションクローズ後の属性アクセスエラーが発生しないこと

    目的: レスポンス返却時にMissingGreenletエラーが発生しないことを確認

    背景:
    - SQLAlchemyの非同期処理で、セッションが閉じられた後にモデル属性にアクセスすると
      MissingGreenletエラーが発生する
    - FastAPIがレスポンスをシリアライズする際、Staffオブジェクトの属性にアクセスする
    - セッションが既に閉じられていると、lazyロードができずエラーが発生

    期待結果:
    - HTTPステータス: 200 OK
    - レスポンスに全ての属性が正しく含まれる（id, last_name, first_name, full_name, etc.）
    - MissingGreenletエラーが発生しない
    """
    # Arrange
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "last_name": "佐藤",
        "first_name": "花子",
        "last_name_furigana": "さとう",
        "first_name_furigana": "はなこ"
    }

    # Act
    response = await async_client.patch(
        "/api/v1/staffs/me/name",
        json=payload,
        headers=headers
    )

    # Assert
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()

    # 全ての属性が正しく含まれることを確認（MissingGreenletエラーが発生していない証拠）
    assert "id" in data, "id field is missing in response"
    assert "last_name" in data, "last_name field is missing in response"
    assert "first_name" in data, "first_name field is missing in response"
    assert "full_name" in data, "full_name field is missing in response"
    assert "last_name_furigana" in data, "last_name_furigana field is missing in response"
    assert "first_name_furigana" in data, "first_name_furigana field is missing in response"
    assert "updated_at" in data, "updated_at field is missing in response"

    # 値が正しいことを確認
    assert data["last_name"] == "佐藤"
    assert data["first_name"] == "花子"
    assert data["full_name"] == "佐藤 花子"
    assert data["last_name_furigana"] == "さとう"
    assert data["first_name_furigana"] == "はなこ"


@pytest.mark.parametrize("mock_current_user", ["test_staff_user"], indirect=True)
async def test_change_password_no_missing_greenlet_error(
    async_client: AsyncClient,
    mock_current_user: Staff,
    db_session: AsyncSession
):
    """
    テストケース65: パスワード変更時のセッション管理が適切であることを確認

    目的: パスワード変更時にもセッションが適切に管理され、MissingGreenletエラーが発生しないことを確認

    期待結果:
    - HTTPステータス: 200 OK
    - レスポンスに必要な属性が正しく含まれる
    - MissingGreenletエラーが発生しない
    """
    # Arrange
    headers = {"Authorization": "Bearer fake-token"}
    payload = {
        "current_password": "a-very-secure-password",
        "new_password": "NewSecure123!",
        "new_password_confirm": "NewSecure123!"
    }

    # Act
    response = await async_client.patch(
        "/api/v1/staffs/me/password",
        json=payload,
        headers=headers
    )

    # Assert
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()

    # レスポンスが正しく返されることを確認（MissingGreenletエラーが発生していない証拠）
    assert "message" in data, "message field is missing in response"
    assert "updated_at" in data, "updated_at field is missing in response"
    assert "logged_out_devices" in data, "logged_out_devices field is missing in response"

    assert data["message"] == "パスワードを変更しました"
    assert isinstance(data["logged_out_devices"], int), "logged_out_devices should be an integer"
