"""
WebhookEvent CRUD操作のテスト
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app import crud
from app.models.webhook_event import WebhookEvent


@pytest.mark.asyncio
class TestWebhookEventCRUD:
    """WebhookEvent CRUD操作のテストクラス"""

    async def test_create_event_record(self, db_session):
        """イベント記録作成のテスト"""
        event_id = f"evt_test_{uuid4().hex[:12]}"
        event_type = "invoice.payment_succeeded"

        webhook_event = await crud.webhook_event.create_event_record(
            db=db_session,
            event_id=event_id,
            event_type=event_type,
            source="stripe",
            status="success"
        )
        await db_session.commit()

        assert webhook_event.event_id == event_id
        assert webhook_event.event_type == event_type
        assert webhook_event.source == "stripe"
        assert webhook_event.status == "success"
        assert webhook_event.processed_at is not None
        assert webhook_event.created_at is not None

    async def test_get_by_event_id(self, db_session):
        """Event IDによる取得のテスト"""
        event_id = f"evt_test_{uuid4().hex[:12]}"

        # イベント作成
        created_event = await crud.webhook_event.create_event_record(
            db=db_session,
            event_id=event_id,
            event_type="customer.subscription.created",
            status="success"
        )
        await db_session.commit()

        # 取得
        retrieved_event = await crud.webhook_event.get_by_event_id(
            db=db_session,
            event_id=event_id
        )

        assert retrieved_event is not None
        assert retrieved_event.id == created_event.id
        assert retrieved_event.event_id == event_id

    async def test_is_event_processed(self, db_session):
        """冪等性チェックのテスト"""
        event_id = f"evt_test_{uuid4().hex[:12]}"

        # 未処理の状態
        is_processed = await crud.webhook_event.is_event_processed(
            db=db_session,
            event_id=event_id
        )
        assert is_processed is False

        # イベント作成
        await crud.webhook_event.create_event_record(
            db=db_session,
            event_id=event_id,
            event_type="invoice.payment_failed",
            status="success"
        )
        await db_session.commit()

        # 処理済みの状態
        is_processed = await crud.webhook_event.is_event_processed(
            db=db_session,
            event_id=event_id
        )
        assert is_processed is True

    async def test_create_event_with_payload(self, db_session):
        """ペイロード付きイベント作成のテスト"""
        event_id = f"evt_test_{uuid4().hex[:12]}"

        webhook_event = await crud.webhook_event.create_event_record(
            db=db_session,
            event_id=event_id,
            event_type="invoice.payment_succeeded",
            payload={"test": "data", "amount": 5000, "currency": "jpy"},
            status="success"
        )
        await db_session.commit()

        assert webhook_event.payload == {"test": "data", "amount": 5000, "currency": "jpy"}
        assert webhook_event.event_id == event_id

    async def test_create_failed_event(self, db_session):
        """失敗イベント記録のテスト"""
        event_id = f"evt_test_{uuid4().hex[:12]}"
        error_message = "Payment method declined"

        webhook_event = await crud.webhook_event.create_event_record(
            db=db_session,
            event_id=event_id,
            event_type="invoice.payment_failed",
            status="failed",
            error_message=error_message
        )
        await db_session.commit()

        assert webhook_event.status == "failed"
        assert webhook_event.error_message == error_message

    async def test_get_recent_events(self, db_session):
        """最近のイベント取得のテスト"""
        # 複数のイベントを作成
        for i in range(5):
            await crud.webhook_event.create_event_record(
                db=db_session,
                event_id=f"evt_recent_{i}",
                event_type="invoice.payment_succeeded",
                status="success"
            )
        await db_session.commit()

        # 取得
        recent_events = await crud.webhook_event.get_recent_events(
            db=db_session,
            limit=3
        )

        assert len(recent_events) >= 3
        # 新しい順にソートされているか確認
        for i in range(len(recent_events) - 1):
            assert recent_events[i].processed_at >= recent_events[i + 1].processed_at

    async def test_get_recent_events_by_type(self, db_session):
        """イベントタイプでフィルタした取得のテスト"""
        # 異なるタイプのイベントを作成
        await crud.webhook_event.create_event_record(
            db=db_session,
            event_id=f"evt_payment_{uuid4().hex[:8]}",
            event_type="invoice.payment_succeeded",
            status="success"
        )
        await crud.webhook_event.create_event_record(
            db=db_session,
            event_id=f"evt_subscription_{uuid4().hex[:8]}",
            event_type="customer.subscription.created",
            status="success"
        )
        await db_session.commit()

        # 特定タイプのみ取得
        payment_events = await crud.webhook_event.get_recent_events(
            db=db_session,
            event_type="invoice.payment_succeeded",
            limit=10
        )

        assert all(e.event_type == "invoice.payment_succeeded" for e in payment_events)

    async def test_get_failed_events(self, db_session):
        """失敗イベント取得のテスト"""
        # 成功と失敗のイベントを作成
        success_event_id = f"evt_success_{uuid4().hex[:8]}"
        failed_event_id = f"evt_failed_{uuid4().hex[:8]}"

        await crud.webhook_event.create_event_record(
            db=db_session,
            event_id=success_event_id,
            event_type="invoice.payment_succeeded",
            status="success"
        )
        await crud.webhook_event.create_event_record(
            db=db_session,
            event_id=failed_event_id,
            event_type="invoice.payment_failed",
            status="failed",
            error_message="Test error"
        )
        await db_session.commit()

        # 失敗イベントのみ取得
        failed_events = await crud.webhook_event.get_failed_events(
            db=db_session,
            limit=10
        )

        assert all(e.status == "failed" for e in failed_events)
        assert any(e.event_id == failed_event_id for e in failed_events)

    async def test_get_failed_events_since(self, db_session):
        """期間指定での失敗イベント取得のテスト"""
        since = datetime.now(timezone.utc) - timedelta(hours=1)

        await crud.webhook_event.create_event_record(
            db=db_session,
            event_id=f"evt_recent_failed_{uuid4().hex[:8]}",
            event_type="invoice.payment_failed",
            status="failed",
            error_message="Recent error"
        )
        await db_session.commit()

        failed_events = await crud.webhook_event.get_failed_events(
            db=db_session,
            since=since,
            limit=10
        )

        assert all(e.processed_at >= since for e in failed_events)

    async def test_cleanup_old_events(self, db_session):
        """古いイベントのクリーンアップのテスト"""
        # このテストは実際のクリーンアップを実行しないが、
        # メソッドが正常に動作することを確認
        deleted_count = await crud.webhook_event.cleanup_old_events(
            db=db_session,
            retention_days=90,
            batch_size=1000
        )
        await db_session.commit()

        # 削除数は0以上であること
        assert deleted_count >= 0

    async def test_duplicate_event_id_prevention(self, db_session):
        """重複Event IDの防止テスト"""
        event_id = f"evt_duplicate_{uuid4().hex[:8]}"

        # 1回目の作成
        await crud.webhook_event.create_event_record(
            db=db_session,
            event_id=event_id,
            event_type="invoice.payment_succeeded",
            status="success"
        )
        await db_session.commit()

        # 2回目の作成（UNIQUE制約違反でエラーになるべき）
        with pytest.raises(Exception):  # IntegrityError
            await crud.webhook_event.create_event_record(
                db=db_session,
                event_id=event_id,
                event_type="invoice.payment_succeeded",
                status="success"
            )
            await db_session.commit()
