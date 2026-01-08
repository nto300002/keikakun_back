"""
Billing操作における監査ログのテスト
"""
import pytest
from uuid import UUID

from app import crud
from app.models.enums import ResourceType, ActionType, BillingStatus


@pytest.mark.asyncio
class TestBillingAuditLog:
    """Billing監査ログのテストクラス"""

    async def test_create_audit_log_for_billing_status_change(self, db_session, staff_factory, office_factory):
        """Billing ステータス変更の監査ログ作成テスト"""
        office = await office_factory(session=db_session, is_test_data=True)
        staff = await staff_factory(office_id=office.id, session=db_session, is_test_data=True)
        billing = await crud.billing.create_for_office(db=db_session, office_id=office.id)
        await db_session.commit()

        # 監査ログ作成
        audit_log = await crud.audit_log.create_log(
            db=db_session,
            actor_id=staff.id,
            action="billing.status_changed",
            target_type="billing",
            target_id=billing.id,
            office_id=office.id,
            ip_address="192.168.1.1",
            user_agent="pytest-test",
            details={
                "old_status": "trial",
                "new_status": "active",
                "reason": "Subscription activated"
            },
            is_test_data=True
        )
        await db_session.commit()

        assert audit_log.staff_id == staff.id
        assert audit_log.office_id == office.id
        assert audit_log.target_type == "billing"
        assert audit_log.target_id == billing.id
        assert audit_log.action == "billing.status_changed"
        assert audit_log.details["old_status"] == "trial"
        assert audit_log.details["new_status"] == "active"

    async def test_get_billing_audit_logs_by_target(self, db_session, staff_factory, office_factory):
        """Billing関連の監査ログ取得テスト"""
        office = await office_factory(session=db_session, is_test_data=True)
        staff = await staff_factory(office_id=office.id, session=db_session, is_test_data=True)
        billing = await crud.billing.create_for_office(db=db_session, office_id=office.id)
        await db_session.commit()

        # 複数の監査ログを作成
        for i in range(3):
            await crud.audit_log.create_log(
                db=db_session,
                actor_id=staff.id,
                action="billing.status_changed",
                target_type="billing",
                target_id=billing.id,
                office_id=office.id,
                ip_address="192.168.1.1",
                user_agent="pytest-test",
                details={"change_number": i},
                is_test_data=True
            )
        await db_session.commit()

        # 取得
        logs = await crud.audit_log.get_logs_by_target(
            db=db_session,
            target_type="billing",
            target_id=billing.id,
            limit=10,
            include_test_data=True
        )

        billing_logs = [log for log in logs if log.target_id == billing.id]
        assert len(billing_logs) >= 3
        assert all(log.target_type == "billing" for log in billing_logs)
