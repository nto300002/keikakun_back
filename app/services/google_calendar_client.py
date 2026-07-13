"""Google Calendar API クライアント

Google Calendar APIとの連携を担当するクライアントクラス
- サービスアカウント方式での認証
- イベントの作成・更新・削除
- エラーハンドリング
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleCalendarAuthenticationError(Exception):
    """Google Calendar認証エラー"""
    pass


class GoogleCalendarAPIError(Exception):
    """Google Calendar API呼び出しエラー"""
    pass


class GoogleCalendarClient:
    """Google Calendar APIクライアント"""

    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self, service_account_json: str):
        """
        Args:
            service_account_json: サービスアカウントJSON文字列
        """
        self.service_account_json = service_account_json
        self.service = None

    def authenticate(self) -> None:
        """サービスアカウントで認証する

        Raises:
            GoogleCalendarAuthenticationError: 認証に失敗した場合
        """
        try:
            # JSONをパース
            service_account_info = json.loads(self.service_account_json)

            logger.info("Google Calendar service account configuration loaded")

            # 認証情報を作成
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=self.SCOPES
            )

            # Calendar APIサービスをビルド
            self.service = build('calendar', 'v3', credentials=credentials)

        except json.JSONDecodeError as e:
            raise GoogleCalendarAuthenticationError(f"カレンダー連携の設定ファイルの形式が正しくありません。")
        except Exception as e:
            raise GoogleCalendarAuthenticationError(f"カレンダー連携の認証に失敗しました。設定ファイルを確認してください。")

    def create_event(
        self,
        calendar_id: str,
        title: str,
        description: str,
        start_datetime: datetime,
        end_datetime: datetime,
        recurrence: Optional[list] = None,
        reminders: Optional[Dict[str, Any]] = None
    ) -> str:
        """カレンダーイベントを作成する

        Args:
            calendar_id: カレンダーID
            title: イベントタイトル
            description: イベント説明
            start_datetime: 開始日時
            end_datetime: 終了日時
            recurrence: 繰り返しルール（RRULE形式）
            reminders: リマインダー設定

        Returns:
            作成されたイベントのID

        Raises:
            GoogleCalendarAPIError: API呼び出しに失敗した場合
        """
        if not self.service:
            raise GoogleCalendarAPIError("カレンダー連携の認証が完了していません。設定を確認してください。")

        logger.info(
            "GoogleCalendarClient.create_event called calendar_id_present=%s title_present=%s",
            bool(calendar_id),
            bool(title),
        )

        # イベントボディを作成
        event_body = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': start_datetime.isoformat(),
                'timeZone': 'Asia/Tokyo',
            },
            'end': {
                'dateTime': end_datetime.isoformat(),
                'timeZone': 'Asia/Tokyo',
            },
        }

        # 繰り返しルールを追加
        if recurrence:
            event_body['recurrence'] = recurrence

        # リマインダーを追加
        if reminders:
            event_body['reminders'] = reminders
        else:
            # デフォルトのリマインダー（毎日午前9時）
            event_body['reminders'] = {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 0},  # イベント時刻にポップアップ
                ],
            }

        try:
            # イベントを作成
            event = self.service.events().insert(
                calendarId=calendar_id,
                body=event_body
            ).execute()

            return event['id']

        except HttpError as e:
            raise GoogleCalendarAPIError(f"カレンダー予定の登録に失敗しました。時間をおいて再度お試しください。")
        except Exception as e:
            raise GoogleCalendarAPIError(f"カレンダー連携で予期しないエラーが発生しました。時間をおいて再度お試しください。")

    def update_event(
        self,
        calendar_id: str,
        event_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        start_datetime: Optional[datetime] = None,
        end_datetime: Optional[datetime] = None,
        recurrence: Optional[list] = None
    ) -> Dict[str, Any]:
        """カレンダーイベントを更新する

        Args:
            calendar_id: カレンダーID
            event_id: イベントID
            title: 新しいイベントタイトル（省略可）
            description: 新しいイベント説明（省略可）
            start_datetime: 新しい開始日時（省略可）
            end_datetime: 新しい終了日時（省略可）
            recurrence: 新しい繰り返しルール（省略可）

        Returns:
            更新されたイベント情報

        Raises:
            GoogleCalendarAPIError: API呼び出しに失敗した場合
        """
        if not self.service:
            raise GoogleCalendarAPIError("カレンダー連携の認証が完了していません。設定を確認してください。")

        try:
            # 既存のイベントを取得
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            # 更新する項目のみ変更
            if title:
                event['summary'] = title
            if description:
                event['description'] = description
            if start_datetime:
                event['start'] = {
                    'dateTime': start_datetime.isoformat(),
                    'timeZone': 'Asia/Tokyo',
                }
            if end_datetime:
                event['end'] = {
                    'dateTime': end_datetime.isoformat(),
                    'timeZone': 'Asia/Tokyo',
                }
            if recurrence:
                event['recurrence'] = recurrence

            # イベントを更新
            updated_event = self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event
            ).execute()

            return updated_event

        except HttpError as e:
            raise GoogleCalendarAPIError(f"カレンダー予定の更新に失敗しました。時間をおいて再度お試しください。")
        except Exception as e:
            raise GoogleCalendarAPIError(f"カレンダー連携で予期しないエラーが発生しました。時間をおいて再度お試しください。")

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        """カレンダーイベントを削除する

        Args:
            calendar_id: カレンダーID
            event_id: イベントID

        Raises:
            GoogleCalendarAPIError: API呼び出しに失敗した場合
        """
        if not self.service:
            raise GoogleCalendarAPIError("カレンダー連携の認証が完了していません。設定を確認してください。")

        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

        except HttpError as e:
            raise GoogleCalendarAPIError(f"カレンダー予定の削除に失敗しました。時間をおいて再度お試しください。")
        except Exception as e:
            raise GoogleCalendarAPIError(f"カレンダー連携で予期しないエラーが発生しました。時間をおいて再度お試しください。")

    def get_event(self, calendar_id: str, event_id: str) -> Dict[str, Any]:
        """カレンダーイベントを取得する

        Args:
            calendar_id: カレンダーID
            event_id: イベントID

        Returns:
            イベント情報

        Raises:
            GoogleCalendarAPIError: API呼び出しに失敗した場合
        """
        if not self.service:
            raise GoogleCalendarAPIError("カレンダー連携の認証が完了していません。設定を確認してください。")

        try:
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            return event

        except HttpError as e:
            raise GoogleCalendarAPIError(f"カレンダー予定の取得に失敗しました。時間をおいて再度お試しください。")
        except Exception as e:
            raise GoogleCalendarAPIError(f"カレンダー連携で予期しないエラーが発生しました。時間をおいて再度お試しください。")
