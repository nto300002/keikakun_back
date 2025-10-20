"""Google Calendar APIクライアントのユニットテスト

TDDアプローチに従って、テストを先に定義してから実装を調整する
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from app.services.google_calendar_client import (
    GoogleCalendarClient,
    GoogleCalendarAuthenticationError,
    GoogleCalendarAPIError
)


# テスト用のサービスアカウントJSON
VALID_SERVICE_ACCOUNT_JSON = json.dumps({
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "test-key-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\ntest-private-key\n-----END PRIVATE KEY-----\n",
    "client_email": "test@test-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
})

INVALID_SERVICE_ACCOUNT_JSON = "this is not valid json"


class TestGoogleCalendarClientAuthentication:
    """認証機能のテスト（UC-1, UC-5）"""

    @patch('app.services.google_calendar_client.build')
    @patch('app.services.google_calendar_client.service_account.Credentials.from_service_account_info')
    def test_authenticate_with_valid_credentials(self, mock_credentials, mock_build):
        """UC-1: 有効なサービスアカウントJSONで認証できる"""
        # Given: 有効なサービスアカウントJSON
        client = GoogleCalendarClient(VALID_SERVICE_ACCOUNT_JSON)
        mock_credentials.return_value = Mock()
        mock_build.return_value = Mock()

        # When: authenticate()を呼び出す
        client.authenticate()

        # Then: 認証が成功する
        assert client.service is not None
        mock_credentials.assert_called_once()
        mock_build.assert_called_once_with('calendar', 'v3', credentials=mock_credentials.return_value)

    def test_authenticate_with_invalid_json(self):
        """UC-5: 無効なJSONで認証エラーが発生する"""
        # Given: 無効なJSON
        client = GoogleCalendarClient(INVALID_SERVICE_ACCOUNT_JSON)

        # When/Then: authenticate()がGoogleCalendarAuthenticationErrorを発生させる
        with pytest.raises(GoogleCalendarAuthenticationError) as exc_info:
            client.authenticate()

        assert "Invalid JSON format" in str(exc_info.value)


class TestGoogleCalendarClientCreateEvent:
    """イベント作成機能のテスト（UC-2）"""

    @pytest.fixture
    def authenticated_client(self):
        """認証済みクライアント"""
        client = GoogleCalendarClient(VALID_SERVICE_ACCOUNT_JSON)
        client.service = Mock()
        return client

    def test_create_event_success(self, authenticated_client):
        """UC-2: イベントを正常に作成できる"""
        # Given: 認証済みクライアントとイベント情報
        calendar_id = "test@group.calendar.google.com"
        title = "テスト太郎 更新期限"
        description = "テスト太郎さんの個別支援計画の更新期限です。"
        start_datetime = datetime.now() + timedelta(days=30)
        end_datetime = start_datetime + timedelta(hours=9)

        # Mockの設定
        mock_event = {'id': 'test-event-id-123'}
        authenticated_client.service.events().insert().execute.return_value = mock_event

        # When: create_event()を呼び出す
        event_id = authenticated_client.create_event(
            calendar_id=calendar_id,
            title=title,
            description=description,
            start_datetime=start_datetime,
            end_datetime=end_datetime
        )

        # Then: イベントIDが返される
        assert event_id == 'test-event-id-123'

        # Then: 正しい引数でAPIが呼ばれる
        call_args = authenticated_client.service.events().insert.call_args
        assert call_args is not None
        assert call_args[1]['calendarId'] == calendar_id

        event_body = call_args[1]['body']
        assert event_body['summary'] == title
        assert event_body['description'] == description
        assert 'start' in event_body
        assert 'end' in event_body

    def test_create_event_with_recurrence(self, authenticated_client):
        """UC-2: 繰り返しルールを持つイベントを作成できる"""
        # Given: 繰り返しルールを含むイベント情報
        calendar_id = "test@group.calendar.google.com"
        title = "繰り返しイベント"
        description = "毎日繰り返すイベント"
        start_datetime = datetime.now()
        end_datetime = start_datetime + timedelta(hours=1)
        recurrence = ['RRULE:FREQ=DAILY;UNTIL=20251231T235959Z']

        mock_event = {'id': 'recurring-event-id'}
        authenticated_client.service.events().insert().execute.return_value = mock_event

        # When: 繰り返しルール付きでcreate_event()を呼び出す
        event_id = authenticated_client.create_event(
            calendar_id=calendar_id,
            title=title,
            description=description,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            recurrence=recurrence
        )

        # Then: イベントIDが返される
        assert event_id == 'recurring-event-id'

        # Then: 繰り返しルールがevent_bodyに含まれる
        call_args = authenticated_client.service.events().insert.call_args
        event_body = call_args[1]['body']
        assert 'recurrence' in event_body
        assert event_body['recurrence'] == recurrence

    def test_create_event_without_authentication(self):
        """UC-2: 未認証の状態でイベント作成を試みるとエラーが発生する"""
        # Given: 未認証のクライアント
        client = GoogleCalendarClient(VALID_SERVICE_ACCOUNT_JSON)

        # When/Then: create_event()がGoogleCalendarAPIErrorを発生させる
        with pytest.raises(GoogleCalendarAPIError) as exc_info:
            client.create_event(
                calendar_id="test@example.com",
                title="Test",
                description="Test",
                start_datetime=datetime.now(),
                end_datetime=datetime.now() + timedelta(hours=1)
            )

        assert "Not authenticated" in str(exc_info.value)


class TestGoogleCalendarClientUpdateEvent:
    """イベント更新機能のテスト（UC-3）"""

    @pytest.fixture
    def authenticated_client(self):
        """認証済みクライアント"""
        client = GoogleCalendarClient(VALID_SERVICE_ACCOUNT_JSON)
        client.service = Mock()
        return client

    def test_update_event_success(self, authenticated_client):
        """UC-3: イベントを正常に更新できる"""
        # Given: 認証済みクライアントと既存のイベント
        calendar_id = "test@group.calendar.google.com"
        event_id = "existing-event-id"
        new_title = "更新されたタイトル"
        new_description = "更新された説明"

        # 既存イベントのモック
        existing_event = {
            'id': event_id,
            'summary': '古いタイトル',
            'description': '古い説明',
            'start': {'dateTime': '2025-01-01T09:00:00+09:00', 'timeZone': 'Asia/Tokyo'},
            'end': {'dateTime': '2025-01-01T18:00:00+09:00', 'timeZone': 'Asia/Tokyo'},
        }

        updated_event = {**existing_event, 'summary': new_title, 'description': new_description}

        authenticated_client.service.events().get().execute.return_value = existing_event
        authenticated_client.service.events().update().execute.return_value = updated_event

        # When: update_event()を呼び出す
        result = authenticated_client.update_event(
            calendar_id=calendar_id,
            event_id=event_id,
            title=new_title,
            description=new_description
        )

        # Then: 更新されたイベントが返される
        assert result['summary'] == new_title
        assert result['description'] == new_description

        # Then: get()とupdate()が呼ばれたことを確認
        get_call_args = authenticated_client.service.events().get.call_args
        assert get_call_args is not None
        update_call_args = authenticated_client.service.events().update.call_args
        assert update_call_args is not None


class TestGoogleCalendarClientDeleteEvent:
    """イベント削除機能のテスト（UC-4）"""

    @pytest.fixture
    def authenticated_client(self):
        """認証済みクライアント"""
        client = GoogleCalendarClient(VALID_SERVICE_ACCOUNT_JSON)
        client.service = Mock()
        return client

    def test_delete_event_success(self, authenticated_client):
        """UC-4: イベントを正常に削除できる"""
        # Given: 認証済みクライアントと既存のイベントID
        calendar_id = "test@group.calendar.google.com"
        event_id = "event-to-delete"

        authenticated_client.service.events().delete().execute.return_value = None

        # When: delete_event()を呼び出す
        authenticated_client.delete_event(calendar_id=calendar_id, event_id=event_id)

        # Then: delete()が呼ばれたことを確認
        call_args = authenticated_client.service.events().delete.call_args
        assert call_args is not None
        assert call_args[1]['calendarId'] == calendar_id
        assert call_args[1]['eventId'] == event_id


class TestGoogleCalendarClientGetEvent:
    """イベント取得機能のテスト"""

    @pytest.fixture
    def authenticated_client(self):
        """認証済みクライアント"""
        client = GoogleCalendarClient(VALID_SERVICE_ACCOUNT_JSON)
        client.service = Mock()
        return client

    def test_get_event_success(self, authenticated_client):
        """イベントを正常に取得できる"""
        # Given: 認証済みクライアントとイベントID
        calendar_id = "test@group.calendar.google.com"
        event_id = "test-event-id"

        mock_event = {
            'id': event_id,
            'summary': 'テストイベント',
            'description': 'テスト説明',
            'start': {'dateTime': '2025-01-01T09:00:00+09:00'},
            'end': {'dateTime': '2025-01-01T18:00:00+09:00'},
        }

        authenticated_client.service.events().get().execute.return_value = mock_event

        # When: get_event()を呼び出す
        result = authenticated_client.get_event(calendar_id=calendar_id, event_id=event_id)

        # Then: イベント情報が返される
        assert result['id'] == event_id
        assert result['summary'] == 'テストイベント'

        # Then: get()が呼ばれたことを確認
        call_args = authenticated_client.service.events().get.call_args
        assert call_args is not None
