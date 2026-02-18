"""
ダッシュボードフィルター機能のテスト用ヘルパー関数

Usage:
    from tests.utils.dashboard_helpers import (
        create_test_office,
        create_test_offices,
        create_test_recipient,
        create_test_recipients,
        create_test_cycle,
        create_test_cycles,
        create_test_status,
        create_test_deliverable
    )
"""

import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Office,
    WelfareRecipient,
    OfficeWelfareRecipient,
    SupportPlanCycle,
    SupportPlanStatus,
    PlanDeliverable
)
from app.models.enums import (
    GenderType,
    SupportPlanStep,
    DeliverableType,
    BillingStatus,
    OfficeType
)
from app.models.billing import Billing


async def create_test_office(
    db: AsyncSession,
    *,
    name: Optional[str] = None,
    billing_status: BillingStatus = BillingStatus.active
) -> Office:
    """
    テスト用の事業所を1件作成する

    Args:
        db: データベースセッション
        name: 事業所名（省略時は自動生成）
        billing_status: 課金ステータス

    Returns:
        作成された事業所
    """
    # まずスタッフを作成（created_by, last_modified_by用）
    from tests.utils.helpers import create_random_staff
    staff = await create_random_staff(db)
    db.add(staff)
    await db.flush()

    if name is None:
        # ランダムな事業所名を生成
        import random
        random_suffix = random.randint(1000, 9999)
        name = f"テスト事業所{random_suffix}"
    else:
        random_suffix = name.split("テスト事業所")[-1] if "テスト事業所" in name else "test"

    office = Office(
        name=name,
        type=OfficeType.transition_to_employment,
        address="東京都渋谷区テスト1-2-3",
        phone_number="03-1234-5678",
        email=f"office{random_suffix}@example.com",
        created_by=staff.id,
        last_modified_by=staff.id,
        is_test_data=True
    )
    db.add(office)
    await db.flush()

    # Billing情報も作成（課金ステータス）
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    billing = Billing(
        office_id=office.id,
        billing_status=billing_status,
        trial_start_date=now,
        trial_end_date=now + timedelta(days=30),
        subscription_start_date=now if billing_status != BillingStatus.free else None
    )
    db.add(billing)
    await db.flush()

    await db.refresh(office)
    return office


async def create_test_offices(
    db: AsyncSession,
    *,
    count: int = 10,
    billing_status: BillingStatus = BillingStatus.active
) -> List[Office]:
    """
    テスト用の事業所を複数件作成する

    Args:
        db: データベースセッション
        count: 作成する事業所数
        billing_status: 課金ステータス

    Returns:
        作成された事業所のリスト
    """
    offices = []
    for i in range(count):
        office = await create_test_office(
            db,
            name=f"テスト事業所{i:04d}",
            billing_status=billing_status
        )
        offices.append(office)

    await db.flush()
    return offices


async def create_test_recipient(
    db: AsyncSession,
    *,
    office_id: uuid.UUID,
    last_name: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name_furigana: Optional[str] = None,
    first_name_furigana: Optional[str] = None,
    birth_day: Optional[date] = None,
    gender: GenderType = GenderType.male
) -> WelfareRecipient:
    """
    テスト用の利用者を1件作成し、事業所に関連付ける

    Args:
        db: データベースセッション
        office_id: 事業所ID
        last_name: 姓
        first_name: 名
        last_name_furigana: 姓（ふりがな）
        first_name_furigana: 名（ふりがな）
        birth_day: 生年月日
        gender: 性別

    Returns:
        作成された利用者
    """
    if last_name is None:
        last_name = "山田"
    if first_name is None:
        first_name = "太郎"
    if last_name_furigana is None:
        last_name_furigana = "やまだ"
    if first_name_furigana is None:
        first_name_furigana = "たろう"
    if birth_day is None:
        birth_day = date(1980, 1, 1)

    recipient = WelfareRecipient(
        last_name=last_name,
        first_name=first_name,
        last_name_furigana=last_name_furigana,
        first_name_furigana=first_name_furigana,
        birth_day=birth_day,
        gender=gender
    )
    db.add(recipient)
    await db.flush()

    # 事業所との関連付け
    association = OfficeWelfareRecipient(
        office_id=office_id,
        welfare_recipient_id=recipient.id
    )
    db.add(association)
    await db.flush()

    await db.refresh(recipient)
    return recipient


async def create_test_recipients(
    db: AsyncSession,
    *,
    office_id: uuid.UUID,
    count: int = 10
) -> List[WelfareRecipient]:
    """
    テスト用の利用者を複数件作成する

    Args:
        db: データベースセッション
        office_id: 事業所ID
        count: 作成する利用者数

    Returns:
        作成された利用者のリスト
    """
    recipients = []
    for i in range(count):
        recipient = await create_test_recipient(
            db,
            office_id=office_id,
            last_name=f"テスト{i:03d}",
            first_name="太郎",
            last_name_furigana=f"てすと{i:03d}",
            first_name_furigana="たろう"
        )
        recipients.append(recipient)

    await db.flush()
    return recipients


async def create_test_cycle(
    db: AsyncSession,
    *,
    welfare_recipient_id: uuid.UUID,
    office_id: uuid.UUID,
    cycle_number: int = 1,
    is_latest_cycle: bool = True,
    next_renewal_deadline: Optional[str] = None,
    plan_cycle_start_date: Optional[date] = None
) -> SupportPlanCycle:
    """
    テスト用の個別支援計画サイクルを1件作成する

    Args:
        db: データベースセッション
        welfare_recipient_id: 利用者ID
        office_id: 事業所ID
        cycle_number: サイクル番号
        is_latest_cycle: 最新サイクルかどうか
        next_renewal_deadline: 次回更新期限（ISO形式文字列: "2026-03-01"）
        plan_cycle_start_date: 計画開始日

    Returns:
        作成されたサイクル
    """
    if plan_cycle_start_date is None:
        plan_cycle_start_date = date.today()

    # next_renewal_deadline が文字列の場合は date に変換
    renewal_deadline_date = None
    if next_renewal_deadline:
        if isinstance(next_renewal_deadline, str):
            renewal_deadline_date = datetime.strptime(next_renewal_deadline, "%Y-%m-%d").date()
        else:
            renewal_deadline_date = next_renewal_deadline

    cycle = SupportPlanCycle(
        welfare_recipient_id=welfare_recipient_id,
        office_id=office_id,
        cycle_number=cycle_number,
        is_latest_cycle=is_latest_cycle,
        plan_cycle_start_date=plan_cycle_start_date,
        next_renewal_deadline=renewal_deadline_date
    )
    db.add(cycle)
    await db.flush()
    await db.refresh(cycle)
    return cycle


async def create_test_cycles(
    db: AsyncSession,
    *,
    welfare_recipient_id: uuid.UUID,
    office_id: uuid.UUID,
    count: int = 3
) -> List[SupportPlanCycle]:
    """
    テスト用の個別支援計画サイクルを複数件作成する

    Args:
        db: データベースセッション
        welfare_recipient_id: 利用者ID
        office_id: 事業所ID
        count: 作成するサイクル数

    Returns:
        作成されたサイクルのリスト
    """
    cycles = []
    for i in range(count):
        is_latest = (i == count - 1)  # 最後のサイクルを最新とする
        cycle = await create_test_cycle(
            db,
            welfare_recipient_id=welfare_recipient_id,
            office_id=office_id,
            cycle_number=i + 1,
            is_latest_cycle=is_latest
        )
        cycles.append(cycle)

    await db.flush()
    return cycles


async def create_test_status(
    db: AsyncSession,
    *,
    plan_cycle_id: int,
    welfare_recipient_id: uuid.UUID,
    office_id: uuid.UUID,
    step_type: SupportPlanStep = SupportPlanStep.assessment,
    is_latest_status: bool = True,
    completed: bool = False,
    completed_at: Optional[datetime] = None
) -> SupportPlanStatus:
    """
    テスト用の個別支援計画ステータスを1件作成する

    Args:
        db: データベースセッション
        plan_cycle_id: サイクルID (Integer)
        welfare_recipient_id: 利用者ID
        office_id: 事業所ID
        step_type: ステップタイプ
        is_latest_status: 最新ステータスかどうか
        completed: 完了済みかどうか
        completed_at: 完了日時

    Returns:
        作成されたステータス
    """
    status = SupportPlanStatus(
        plan_cycle_id=plan_cycle_id,
        welfare_recipient_id=welfare_recipient_id,
        office_id=office_id,
        step_type=step_type,
        is_latest_status=is_latest_status,
        completed=completed,
        completed_at=completed_at
    )
    db.add(status)
    await db.flush()
    await db.refresh(status)
    return status


async def create_test_deliverable(
    db: AsyncSession,
    *,
    plan_cycle_id: int,
    deliverable_type: DeliverableType = DeliverableType.assessment_sheet,
    file_path: Optional[str] = None,
    original_filename: Optional[str] = None
) -> PlanDeliverable:
    """
    テスト用のデリバラブル（成果物）を1件作成する

    Args:
        db: データベースセッション
        plan_cycle_id: サイクルID (Integer)
        deliverable_type: デリバラブルタイプ
        file_path: ファイルパス
        original_filename: 元のファイル名

    Returns:
        作成されたデリバラブル
    """
    if file_path is None:
        file_path = f"/test/{deliverable_type.value}_{plan_cycle_id}.pdf"
    if original_filename is None:
        original_filename = f"{deliverable_type.value}_{plan_cycle_id}.pdf"

    deliverable = PlanDeliverable(
        plan_cycle_id=plan_cycle_id,
        deliverable_type=deliverable_type,
        file_path=file_path,
        original_filename=original_filename
    )
    db.add(deliverable)
    await db.flush()
    await db.refresh(deliverable)
    return deliverable


# 後方互換性のため、tests.utils からインポート可能にする
__all__ = [
    "create_test_office",
    "create_test_offices",
    "create_test_recipient",
    "create_test_recipients",
    "create_test_cycle",
    "create_test_cycles",
    "create_test_status",
    "create_test_deliverable",
]
