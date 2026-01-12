# tests/api/v1/test_dashboard.py

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta

# 修正: 依存性オーバーライドのためにappとget_current_userをインポート
from app.main import app
from app.api.deps import get_current_user

from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.billing import Billing
from app.models.enums import StaffRole, OfficeType, GenderType, SupportPlanStep, BillingStatus

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


@pytest.fixture
async def dashboard_fixtures(db_session: AsyncSession, service_admin_user_factory, office_factory):
    """ダッシュボードテスト用の基本フィクスチャ"""
    from datetime import timezone, timedelta

    staff = await service_admin_user_factory(first_name="管理者", last_name="ダッシュボードテスト", email="dashboard@example.com", role=StaffRole.owner)
    office = await office_factory(creator=staff, name="テストダッシュボード事業所", type=OfficeType.type_A_office)
    office_staff = OfficeStaff(staff_id=staff.id, office_id=office.id, is_primary=True)
    db_session.add(office_staff)
    
    recipients = []
    for i in range(3):
        recipient = WelfareRecipient(
            first_name=f"太郎{i+1}", 
            last_name="田中", 
            first_name_furigana=f"たろう{i+1}",
            last_name_furigana="たなか",
            birth_day=date(1990, 1, 1), 
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()
        office_recipient = OfficeWelfareRecipient(welfare_recipient_id=recipient.id, office_id=office.id)
        db_session.add(office_recipient)
        recipients.append(recipient)
    
    for i, recipient in enumerate(recipients):
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            plan_cycle_start_date=date.today() - timedelta(days=30),
            next_renewal_deadline=date.today() + timedelta(days=150),
            is_latest_cycle=True,
            cycle_number=1
        )
        db_session.add(cycle)
        await db_session.flush()
        if i == 0:
            status1 = SupportPlanStatus(
                plan_cycle_id=cycle.id,
                welfare_recipient_id=recipient.id,
                office_id=office.id,
                step_type=SupportPlanStep.assessment,
                completed=True
            )
            status2 = SupportPlanStatus(
                plan_cycle_id=cycle.id,
                welfare_recipient_id=recipient.id,
                office_id=office.id,
                step_type=SupportPlanStep.draft_plan,
                completed=False
            )
            db_session.add_all([status1, status2])
        elif i == 1:
            cycle.next_plan_start_date = 7
            status = SupportPlanStatus(
                plan_cycle_id=cycle.id,
                welfare_recipient_id=recipient.id,
                office_id=office.id,
                step_type=SupportPlanStep.monitoring,
                completed=False
            )
            db_session.add(status)

    # Billing情報を作成 (dashboardエンドポイントで必要)
    billing = Billing(
        office_id=office.id,
        billing_status=BillingStatus.free,
        trial_start_date=date.today(),
        trial_end_date=date.today() + timedelta(days=180),
        current_plan_amount=6000
    )
    db_session.add(billing)

    await db_session.commit()
    return {'staff': staff, 'office': office, 'recipients': recipients}


class TestDashboardAPI:
    """ダッシュボードAPIのテストクラス"""
    
    async def test_get_dashboard_success(self, async_client: AsyncClient, dashboard_fixtures):
        staff = dashboard_fixtures['staff']
        async def override_get_current_user():
            return staff
        app.dependency_overrides[get_current_user] = override_get_current_user

        response = await async_client.get("/api/v1/dashboard/")

        del app.dependency_overrides[get_current_user]

        if response.status_code != 200:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
        assert response.status_code == 200
        data = response.json()
        assert data["staff_name"] == staff.full_name
        assert data["office_name"] == dashboard_fixtures['office'].name
        assert data["current_user_count"] == 3
        assert len(data["recipients"]) == 3

        # next_plan_start_date が設定されている利用者を確認
        recipient_with_monitoring = next(
            (r for r in data["recipients"] if r.get("next_plan_start_date") is not None),
            None
        )
        assert recipient_with_monitoring is not None
        assert recipient_with_monitoring["next_plan_start_date"] == 7

    async def test_get_dashboard_empty_recipients(self, async_client: AsyncClient, db_session: AsyncSession, service_admin_user_factory, office_factory):
        staff = await service_admin_user_factory(first_name="管理者", last_name="空の事業所", email="empty@example.com")
        office = await office_factory(creator=staff, name="空のテスト事業所")
        office_staff = OfficeStaff(staff_id=staff.id, office_id=office.id, is_primary=True)
        db_session.add(office_staff)

        # Billing情報を作成 (dashboardエンドポイントで必要)
        from datetime import timedelta
        billing = Billing(
            office_id=office.id,
            billing_status=BillingStatus.free,
            trial_start_date=date.today(),
            trial_end_date=date.today() + timedelta(days=180),
            current_plan_amount=6000
        )
        db_session.add(billing)

        await db_session.commit()

        async def override_get_current_user():
            return staff
        app.dependency_overrides[get_current_user] = override_get_current_user
        response = await async_client.get("/api/v1/dashboard/")
        del app.dependency_overrides[get_current_user]
        
        assert response.status_code == 200
        data = response.json()
        assert data["current_user_count"] == 0
        assert data["recipients"] == []

    async def test_get_dashboard_unauthorized(self, async_client: AsyncClient):
        # 認証オーバーライドなしでアクセス
        response = await async_client.get("/api/v1/dashboard/")
        assert response.status_code == 401

    async def test_get_dashboard_no_office_association(self, async_client: AsyncClient, db_session: AsyncSession, service_admin_user_factory):
        staff = await service_admin_user_factory(first_name="スタッフ", last_name="無所属", email="nooffice@example.com")
        await db_session.commit()

        app.dependency_overrides[get_current_user] = lambda: staff
        response = await async_client.get("/api/v1/dashboard/")
        del app.dependency_overrides[get_current_user]

        assert response.status_code == 404
        assert "事業所情報が見つかりません" in response.json()["detail"]

    async def test_get_dashboard_next_plan_start_days_remaining(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        service_admin_user_factory,
        office_factory
    ):
        """
        次回開始期限の残り日数計算テスト

        条件:
        - is_latest_cycle=true
        - アセスメントPDFがアップロードされていない
        - next_plan_start_dateが設定されている
        - 前サイクルのfinal_plan_signed完了日がある

        期待:
        - next_plan_start_days_remainingフィールドに残り日数が返される
        - 計算式: (前サイクルfinal_plan_signed完了日 + next_plan_start_date) - 現在日付
        """
        from datetime import datetime, timezone

        staff = await service_admin_user_factory(
            first_name="管理者",
            last_name="次回期限テスト",
            email="nextplan@example.com",
            role=StaffRole.owner
        )
        office = await office_factory(
            creator=staff,
            name="次回期限テスト事業所",
            type=OfficeType.type_A_office
        )
        office_staff = OfficeStaff(staff_id=staff.id, office_id=office.id, is_primary=True)
        db_session.add(office_staff)

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="太郎",
            last_name="山田",
            first_name_furigana="たろう",
            last_name_furigana="やまだ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        office_recipient = OfficeWelfareRecipient(
            welfare_recipient_id=recipient.id,
            office_id=office.id
        )
        db_session.add(office_recipient)

        # 前サイクル（cycle_number=1）を作成
        prev_cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            plan_cycle_start_date=date.today() - timedelta(days=180),
            next_renewal_deadline=date.today() - timedelta(days=30),
            is_latest_cycle=False,
            cycle_number=1
        )
        db_session.add(prev_cycle)
        await db_session.flush()

        # 前サイクルのfinal_plan_signedステータスを完了させる（10日前に完了）
        final_plan_completed_date = datetime.now(timezone.utc) - timedelta(days=10)
        prev_final_status = SupportPlanStatus(
            plan_cycle_id=prev_cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.final_plan_signed,
            completed=True,
            completed_at=final_plan_completed_date
        )
        db_session.add(prev_final_status)

        # 現在のサイクル（cycle_number=2、is_latest_cycle=true）を作成
        current_cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            plan_cycle_start_date=date.today() - timedelta(days=30),
            next_renewal_deadline=date.today() + timedelta(days=150),
            is_latest_cycle=True,
            cycle_number=2,
            next_plan_start_date=7  # 7日後が期限
        )
        db_session.add(current_cycle)
        await db_session.flush()

        # 現在のサイクルにアセスメントステータスを追加（完了済み）
        assessment_status = SupportPlanStatus(
            plan_cycle_id=current_cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.assessment,
            completed=True
        )
        db_session.add(assessment_status)

        # 注意: アセスメントPDFはアップロードしない（deliverableを作成しない）

        # Billing情報を作成
        billing = Billing(
            office_id=office.id,
            billing_status=BillingStatus.free,
            trial_start_date=date.today(),
            trial_end_date=date.today() + timedelta(days=180),
            current_plan_amount=6000
        )
        db_session.add(billing)

        await db_session.commit()

        # APIを呼び出し
        app.dependency_overrides[get_current_user] = lambda: staff
        response = await async_client.get("/api/v1/dashboard/")
        del app.dependency_overrides[get_current_user]

        # レスポンスの検証
        assert response.status_code == 200
        data = response.json()

        recipients = data["recipients"]
        assert len(recipients) == 1

        recipient_data = recipients[0]

        # next_plan_start_days_remainingフィールドが存在することを確認
        assert "next_plan_start_days_remaining" in recipient_data

        # 期待される残り日数を計算
        # 期限日 = 前サイクルfinal_plan_signed完了日 + next_plan_start_date（7日）
        # 10日前 + 7日 = 3日前（マイナス3日）となるはず
        expected_deadline = final_plan_completed_date.date() + timedelta(days=7)
        expected_days_remaining = (expected_deadline - date.today()).days

        # 実際の残り日数を確認（-3日または近い値）
        assert recipient_data["next_plan_start_days_remaining"] == expected_days_remaining
        assert recipient_data["next_plan_start_days_remaining"] < 0  # 期限切れ

    async def test_get_dashboard_next_plan_start_days_remaining_cycle1(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        service_admin_user_factory,
        office_factory
    ):
        """
        1サイクル目の次回開始期限の残り日数計算テスト

        条件:
        - cycle_number=1（1サイクル目）
        - is_latest_cycle=true
        - アセスメントPDFがアップロードされていない
        - next_plan_start_dateが設定されている

        期待:
        - next_plan_start_days_remainingフィールドに残り日数が返される
        - 計算式: (サイクル開始日 + next_plan_start_date) - 現在日付
        """
        from datetime import datetime, timezone

        staff = await service_admin_user_factory(
            first_name="管理者",
            last_name="1サイクル期限テスト",
            email="cycle1nextplan@example.com",
            role=StaffRole.owner
        )
        office = await office_factory(
            creator=staff,
            name="1サイクル期限テスト事業所",
            type=OfficeType.type_A_office
        )
        office_staff = OfficeStaff(staff_id=staff.id, office_id=office.id, is_primary=True)
        db_session.add(office_staff)

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="太郎",
            last_name="山田",
            first_name_furigana="たろう",
            last_name_furigana="やまだ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # 事業所と利用者の関連を作成
        office_recipient = OfficeWelfareRecipient(
            welfare_recipient_id=recipient.id,
            office_id=office.id
        )
        db_session.add(office_recipient)

        # 1サイクル目を作成（10日前に開始）
        cycle_start_date = datetime.now(timezone.utc) - timedelta(days=10)
        cycle1 = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True,
            plan_cycle_start_date=cycle_start_date.date(),
            next_plan_start_date=7  # 7日後にアセスメント開始
        )
        db_session.add(cycle1)
        await db_session.flush()

        # アセスメント等のステータスは作成しない（アセスメント未完了）

        # Billing情報を作成
        billing = Billing(
            office_id=office.id,
            billing_status=BillingStatus.free,
            trial_start_date=date.today(),
            trial_end_date=date.today() + timedelta(days=180),
            current_plan_amount=6000
        )
        db_session.add(billing)

        await db_session.commit()

        # 依存性オーバーライドでスタッフを設定
        async def override_get_current_user():
            return staff
        app.dependency_overrides[get_current_user] = override_get_current_user

        # ダッシュボードAPIを呼び出し
        response = await async_client.get("/api/v1/dashboard/")

        # オーバーライドをクリーンアップ
        del app.dependency_overrides[get_current_user]

        assert response.status_code == 200
        data = response.json()

        recipients = data["recipients"]
        assert len(recipients) == 1

        recipient_data = recipients[0]

        # next_plan_start_days_remainingフィールドが存在することを確認
        assert "next_plan_start_days_remaining" in recipient_data

        # 期待される残り日数を計算
        # 期限日 = サイクル開始日 + next_plan_start_date（7日）
        # 10日前 + 7日 = 3日前（マイナス3日）となるはず
        expected_deadline = cycle_start_date.date() + timedelta(days=7)
        expected_days_remaining = (expected_deadline - date.today()).days

        # 実際の残り日数を確認（-3日または近い値）
        assert recipient_data["next_plan_start_days_remaining"] == expected_days_remaining
        assert recipient_data["next_plan_start_days_remaining"] < 0  # 期限切れ
