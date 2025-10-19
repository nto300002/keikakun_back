"""Google Calendar API データ構造調査テスト（統合テスト）

Phase 1-1: Google Calendar APIのイベント作成レスポンス構造を検証

このテストは実際のGoogle Calendar APIと連携して以下を確認します:
- イベントが正常に作成されるか
- イベントIDが返されるか
- Google Calendar上でイベントが検索可能か

実行条件:
- TEST_SERVICE_ACCOUNT_JSON環境変数が設定されている
- TEST_GOOGLE_CALENDAR_ID環境変数が設定されている
- Google Calendarとサービスアカウントが共有されている

実行コマンド:
pytest tests/integration/test_google_calendar_api_structure.py -v -s --tb=short -m integration
"""

import pytest
from datetime import datetime, timedelta
from app.services.google_calendar_client import GoogleCalendarClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_event_response_structure(
    db_session,
    calendar_account_fixture,
    welfare_recipient_fixture
):
    """Google Calendar APIのイベント作成レスポンス構造を検証

    テスト内容:
    1. サービスアカウントで認証
    2. テストイベントを作成
    3. イベントIDが返されることを確認
    4. イベントIDが文字列で空でないことを確認
    5. 作成したイベントを削除（クリーンアップ）
    """
    # Arrange
    service_account_json = calendar_account_fixture.decrypt_service_account_key()
    client = GoogleCalendarClient(service_account_json)
    client.authenticate()

    test_title = f"{welfare_recipient_fixture.last_name} {welfare_recipient_fixture.first_name} 更新期限"
    test_start = datetime.now()
    test_end = test_start + timedelta(days=30)

    # Act
    event_id = client.create_event(
        calendar_id=calendar_account_fixture.google_calendar_id,
        title=test_title,
        description="テストイベント",
        start_datetime=test_start,
        end_datetime=test_end
    )

    # Assert
    assert event_id is not None, "イベントIDがNoneです"
    assert isinstance(event_id, str), f"イベントIDが文字列ではありません: {type(event_id)}"
    assert len(event_id) > 0, "イベントIDが空文字列です"

    print(f"\n✅ イベント作成成功: {event_id}")
    print(f"   タイトル: {test_title}")
    print(f"   カレンダーID: {calendar_account_fixture.google_calendar_id}")

    # Cleanup
    client.delete_event(
        calendar_id=calendar_account_fixture.google_calendar_id,
        event_id=event_id
    )

    print(f"✅ テストイベント削除成功")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_searchable_on_google_calendar(
    db_session,
    calendar_account_fixture,
    welfare_recipient_fixture
):
    """Google Calendar上でイベントが検索可能か確認

    テスト内容:
    1. 「更新期限」というキーワードを含むイベントを作成
    2. Google Calendar APIでイベントを再取得
    3. イベント情報が正しいことを確認
    4. summaryに「更新期限」が含まれることを確認
    5. 作成したイベントを削除（クリーンアップ）
    """
    # Arrange
    service_account_json = calendar_account_fixture.decrypt_service_account_key()
    client = GoogleCalendarClient(service_account_json)
    client.authenticate()

    test_title = f"{welfare_recipient_fixture.last_name} {welfare_recipient_fixture.first_name} 更新期限"
    test_start = datetime.now()
    test_end = test_start + timedelta(days=30)

    # Act
    event_id = client.create_event(
        calendar_id=calendar_account_fixture.google_calendar_id,
        title=test_title,
        description="検索テスト",
        start_datetime=test_start,
        end_datetime=test_end
    )

    # Google Calendar APIでイベントを取得
    event = client.get_event(
        calendar_id=calendar_account_fixture.google_calendar_id,
        event_id=event_id
    )

    # Assert
    assert event['summary'] == test_title, f"イベントタイトルが一致しません: {event['summary']}"
    assert '更新期限' in event['summary'], "イベントタイトルに「更新期限」が含まれていません"
    assert event['id'] == event_id, f"イベントIDが一致しません: {event['id']}"

    print(f"\n✅ イベント取得成功: {event_id}")
    print(f"   タイトル: {event['summary']}")
    print(f"   説明: {event.get('description', 'N/A')}")
    print(f"   開始: {event['start']}")
    print(f"   終了: {event['end']}")

    # Cleanup
    client.delete_event(
        calendar_id=calendar_account_fixture.google_calendar_id,
        event_id=event_id
    )

    print(f"✅ テストイベント削除成功")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_with_daily_reminder(
    db_session,
    calendar_account_fixture,
    welfare_recipient_fixture
):
    """毎日のリマインダー付きイベントが作成できることを確認

    テスト内容:
    1. 毎日のリマインダー設定を持つイベントを作成
    2. イベント作成後にAPIで取得
    3. リマインダー設定が正しく保存されていることを確認
    4. 作成したイベントを削除（クリーンアップ）
    """
    # Arrange
    service_account_json = calendar_account_fixture.decrypt_service_account_key()
    client = GoogleCalendarClient(service_account_json)
    client.authenticate()

    test_title = f"{welfare_recipient_fixture.last_name} {welfare_recipient_fixture.first_name} モニタリング期限"
    test_start = datetime.now() + timedelta(days=7)
    test_end = test_start.replace(hour=18)

    # 毎日のポップアップリマインダー
    reminders = {
        'useDefault': False,
        'overrides': [
            {'method': 'popup', 'minutes': 0},  # イベント時刻にポップアップ
        ],
    }

    # Act
    event_id = client.create_event(
        calendar_id=calendar_account_fixture.google_calendar_id,
        title=test_title,
        description="モニタリング期限テスト",
        start_datetime=test_start,
        end_datetime=test_end,
        reminders=reminders
    )

    # イベントを取得してリマインダー設定を確認
    event = client.get_event(
        calendar_id=calendar_account_fixture.google_calendar_id,
        event_id=event_id
    )

    # Assert
    assert event_id is not None
    assert 'reminders' in event, "リマインダー設定が含まれていません"
    assert event['reminders']['useDefault'] is False, "デフォルトリマインダーが無効化されていません"
    assert len(event['reminders']['overrides']) > 0, "カスタムリマインダーが設定されていません"

    print(f"\n✅ リマインダー付きイベント作成成功: {event_id}")
    print(f"   タイトル: {event['summary']}")
    print(f"   リマインダー: {event['reminders']}")

    # Cleanup
    client.delete_event(
        calendar_id=calendar_account_fixture.google_calendar_id,
        event_id=event_id
    )

    print(f"✅ テストイベント削除成功")
