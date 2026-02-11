"""
後方互換性テスト: Gmail期限通知バッチ処理

目的:
- 最適化により既存機能が破壊されていないことを確認
- dry_runモード、閾値フィルタリング、監査ログが正しく動作することを確認

テストケース:
- Test 7.1: dry_runモードが正しく動作するか
- Test 7.2: 閾値フィルタリングが正しく動作するか
- Test 7.3: 監査ログが正確に記録されるか
"""
import pytest
import pytest_asyncio
from datetime import date, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.deadline_notification import send_deadline_alert_emails
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, PlanDeliverable
from app.models.enums import DeliverableType


@pytest.fixture(autouse=True)
def mock_weekday_check():
    """
    すべてのテストで週末・祝日チェックをスキップ
    テストは曜日に関係なく実行できるようにする
    """
    with patch('app.tasks.deadline_notification.is_japanese_weekday_and_not_holiday', return_value=True):
        yield


# ==================== Test 7.1: dry_runモード ====================

@pytest.mark.asyncio
async def test_backward_compatibility_dry_run_mode(
    db_session: AsyncSession,
    office_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    Test 7.1: dry_runモードが正しく動作するか

    検証内容:
    - dry_run=Trueの場合、メールは送信されない
    - 送信予定件数は正しくカウントされる
    - 監査ログは作成されない（dry_runなので）

    期待結果:
    - result['email_sent'] > 0（カウントはされる）
    - 実際のメール送信は行われない
    - 監査ログは作成されない
    """
    print("\n" + "="*70)
    print("📊 Test 7.1: dry_runモード後方互換性テスト")
    print("="*70)

    # テストデータ生成（既存のテストパターンに従う）
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(
        staff_id=test_admin_user.id,
        office_id=office.id,
        is_primary=True,
        is_test_data=True
    ))
    await db_session.flush()

    # 1人の利用者 + アラートを作成
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=15),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7,
        is_test_data=True
    )
    db_session.add(cycle)
    await db_session.flush()
    await db_session.commit()

    # dry_run=Trueでバッチ処理実行
    with patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_create_log:

        result = await send_deadline_alert_emails(db=db_session, dry_run=True)

        # 結果表示
        print(f"\n📈 測定結果:")
        print(f"  📧 送信メール数（カウント）: {result['email_sent']}件")
        print(f"  ✉️  実際のメール送信呼び出し: {mock_send_email.call_count}回")
        print(f"  📝 監査ログ作成呼び出し: {mock_create_log.call_count}回")

        # 検証
        # dry_run=Trueなので、1件のメールがカウントされる（test_admin_userに送信）
        assert result['email_sent'] == 1, \
            f"送信メール数（カウント）が期待値と異なる: {result['email_sent']} != 1"

        # 実際のメール送信は呼び出されない
        assert mock_send_email.call_count == 0, \
            f"dry_runモードなのにメール送信が呼び出されました: {mock_send_email.call_count}回"

        # 監査ログも作成されない
        assert mock_create_log.call_count == 0, \
            f"dry_runモードなのに監査ログが作成されました: {mock_create_log.call_count}回"

        print("✅ dry_runモードが正しく動作しています")


# ==================== Test 7.2: 閾値フィルタリング ====================

@pytest.mark.asyncio
async def test_backward_compatibility_threshold_filtering(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    Test 7.2: 閾値フィルタリングが正しく動作するか

    検証内容:
    - スタッフの email_threshold_days 設定に基づいてアラートがフィルタリングされる
    - Staff A: email_threshold_days=10 → 15日後のアラートは送信されない（15 > 10）
    - Staff B: email_threshold_days=20 → 15日後のアラートは送信される（15 <= 20）

    期待結果:
    - Staff Aには送信されない
    - Staff Bには送信される
    - 合計1件の送信
    """
    print("\n" + "="*70)
    print("📊 Test 7.2: 閾値フィルタリング後方互換性テスト")
    print("="*70)

    # テストデータ生成
    office = await office_factory(
        creator=test_admin_user,
        name="閾値テスト事業所"
    )

    # Staff A: 閾値10日（15日後のアラートは受け取らない）
    staff_a = await staff_factory(
        office_id=office.id,
        email="threshold_staff_a@example.com"
    )
    staff_a.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "email_threshold_days": 10,  # 10日以内のアラートのみ
        "push_threshold_days": 10
    }
    db_session.add(staff_a)
    db_session.add(OfficeStaff(
        staff_id=staff_a.id,
        office_id=office.id,
        is_primary=True,
        is_test_data=True
    ))

    # Staff B: 閾値20日（15日後のアラートを受け取る）
    staff_b = await staff_factory(
        office_id=office.id,
        email="threshold_staff_b@example.com"
    )
    staff_b.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "email_threshold_days": 20,  # 20日以内のアラートを受け取る
        "push_threshold_days": 10
    }
    db_session.add(staff_b)
    db_session.add(OfficeStaff(
        staff_id=staff_b.id,
        office_id=office.id,
        is_primary=True,
        is_test_data=True
    ))

    await db_session.flush()

    # 1人の利用者 + 15日後のアラートを作成
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=15),  # 15日後
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=22,
        is_test_data=True
    )
    db_session.add(cycle)
    await db_session.flush()  # cycle.idを取得するためにflush

    # アセスメントPDFをアップロード済みにして、assessment_incompleteアラートを抑制
    deliverable = PlanDeliverable(
        plan_cycle_id=cycle.id,
        deliverable_type=DeliverableType.assessment_sheet,
        file_path="/test/assessment.pdf",
        original_filename="assessment.pdf",
        uploaded_by=test_admin_user.id,
        is_test_data=True
    )
    db_session.add(deliverable)
    await db_session.commit()

    # バッチ処理実行
    result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    # 結果表示
    print(f"\n📈 測定結果:")
    print(f"  📧 送信メール数: {result['email_sent']}件")
    print(f"  👤 Staff A (閾値10日): 受信しない（15日後 > 10日）")
    print(f"  👤 Staff B (閾値20日): 受信する（15日後 <= 20日）")

    # 検証
    # Staff Bのみ受信するので、1件
    assert result['email_sent'] == 1, \
        f"送信メール数が期待値と異なる: {result['email_sent']} != 1"

    print("✅ 閾値フィルタリングが正しく動作しています")


# ==================== Test 7.3: 監査ログ ====================

@pytest.mark.asyncio
async def test_backward_compatibility_audit_logs(
    db_session: AsyncSession,
    office_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    Test 7.3: 監査ログが正確に記録されるか

    検証内容:
    - 各メール送信時に監査ログが作成される
    - 監査ログに必要な情報が含まれている
      - action: "deadline_notification_sent"
      - target_type: "email_notification"
      - details: renewal_alert_count, assessment_alert_count

    期待結果:
    - 送信メール数と同じ数の監査ログが作成される
    - 各ログに必要な情報が含まれている
    """
    print("\n" + "="*70)
    print("📊 Test 7.3: 監査ログ後方互換性テスト")
    print("="*70)

    # テストデータ生成
    office = await office_factory(
        creator=test_admin_user,
        name="監査ログテスト事業所"
    )
    db_session.add(OfficeStaff(
        staff_id=test_admin_user.id,
        office_id=office.id,
        is_primary=True,
        is_test_data=True
    ))
    await db_session.flush()

    # 1人の利用者 + アラートを作成
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=15),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7,
        is_test_data=True
    )
    db_session.add(cycle)
    await db_session.flush()
    await db_session.commit()

    # バッチ処理実行（dry_run=Falseで監査ログを作成）
    with patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_create_log:

        mock_send_email.return_value = AsyncMock()
        mock_create_log.return_value = AsyncMock()

        result = await send_deadline_alert_emails(db=db_session, dry_run=False)

        # 結果表示
        print(f"\n📈 測定結果:")
        print(f"  📧 送信メール数: {result['email_sent']}件")
        print(f"  📝 監査ログ作成呼び出し: {mock_create_log.call_count}回")

        # 検証
        # 1人のスタッフ（test_admin_user）に送信されるので、1件
        assert result['email_sent'] == 1, \
            f"送信メール数が期待値と異なる: {result['email_sent']} != 1"

        # 監査ログも1件作成される
        assert mock_create_log.call_count == 1, \
            f"監査ログ作成回数が期待値と異なる: {mock_create_log.call_count} != 1"

        # 各監査ログの内容を検証
        for call_idx, call in enumerate(mock_create_log.call_args_list):
            kwargs = call.kwargs
            print(f"\n  📝 監査ログ {call_idx + 1}:")
            print(f"     - action: {kwargs.get('action')}")
            print(f"     - target_type: {kwargs.get('target_type')}")
            print(f"     - details keys: {list(kwargs.get('details', {}).keys())}")

            # action の検証
            assert kwargs.get('action') == 'deadline_notification_sent', \
                f"actionが不正: {kwargs.get('action')}"

            # target_type の検証
            assert kwargs.get('target_type') == 'email_notification', \
                f"target_typeが不正: {kwargs.get('target_type')}"

            # details の検証
            details = kwargs.get('details', {})
            assert 'renewal_alert_count' in details, "renewal_alert_countがdetailsに含まれていません"
            assert 'assessment_alert_count' in details, "assessment_alert_countがdetailsに含まれていません"

        print("\n✅ 監査ログが正確に記録されています")


# ==================== 統合テスト ====================

@pytest.mark.asyncio
async def test_backward_compatibility_integration(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    統合テスト: dry_run + 閾値フィルタリング + 監査ログの組み合わせ

    検証内容:
    - すべての機能が組み合わさって正しく動作することを確認

    テストシナリオ:
    1. 2つの事業所を作成
    2. 各事業所に閾値の異なるスタッフを配置
    3. dry_run=Falseで実行
    4. 閾値に応じたフィルタリングと監査ログ作成を確認
    """
    print("\n" + "="*70)
    print("📊 統合テスト: 後方互換性総合テスト")
    print("="*70)

    # テストデータ生成
    offices = []
    expected_email_count = 0

    for office_idx in range(2):
        office = await office_factory(
            creator=test_admin_user,
            name=f"統合テスト事業所{office_idx + 1}"
        )
        offices.append(office)

        # 各事業所に2人のスタッフ（閾値が異なる）
        for staff_idx in range(2):
            threshold = 10 if staff_idx == 0 else 20
            staff = await staff_factory(
                office_id=office.id,
                email=f"integration_staff_{office_idx}_{staff_idx}@example.com"
            )
            staff.notification_preferences = {
                "in_app_notification": True,
                "email_notification": True,
                "email_threshold_days": threshold,
                "push_threshold_days": threshold
            }
            db_session.add(staff)
            db_session.add(OfficeStaff(
                staff_id=staff.id,
                office_id=office.id,
                is_primary=True,
                is_test_data=True
            ))

            # 閾値20日のスタッフのみ受信する（15日後のアラート）
            if threshold == 20:
                expected_email_count += 1

        await db_session.flush()

        # 各事業所に1人の利用者 + 15日後のアラート
        recipient = await welfare_recipient_factory(office_id=office.id)
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            next_renewal_deadline=date.today() + timedelta(days=15),
            is_latest_cycle=True,
            cycle_number=1,
            next_plan_start_date=22,
            is_test_data=True
        )
        db_session.add(cycle)
        await db_session.flush()  # cycle.idを取得するためにflush

        # アセスメントPDFをアップロード
        deliverable = PlanDeliverable(
            plan_cycle_id=cycle.id,
            deliverable_type=DeliverableType.assessment_sheet,
            file_path=f"/test/assessment_{office_idx}.pdf",
            original_filename=f"assessment_{office_idx}.pdf",
            uploaded_by=test_admin_user.id,
            is_test_data=True
        )
        db_session.add(deliverable)

    await db_session.commit()

    # バッチ処理実行
    with patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_create_log:

        mock_send_email.return_value = AsyncMock()
        mock_create_log.return_value = AsyncMock()

        result = await send_deadline_alert_emails(db=db_session, dry_run=False)

        # 結果表示
        print(f"\n📈 測定結果:")
        print(f"  🏢 事業所数: {len(offices)}")
        print(f"  📧 送信メール数: {result['email_sent']}件")
        print(f"  📧 期待送信数: {expected_email_count}件")
        print(f"  📝 監査ログ作成: {mock_create_log.call_count}回")

        # 検証
        # 2事業所 × 1人（閾値20日のスタッフのみ）= 2件
        assert result['email_sent'] == expected_email_count, \
            f"送信メール数が期待値と異なる: {result['email_sent']} != {expected_email_count}"

        # 監査ログも同数作成される
        assert mock_create_log.call_count == expected_email_count, \
            f"監査ログ作成数が期待値と異なる: {mock_create_log.call_count} != {expected_email_count}"

        print("\n✅ すべての機能が正しく統合されています")
        print("   - dry_runモード: 正常")
        print("   - 閾値フィルタリング: 正常")
        print("   - 監査ログ記録: 正常")
