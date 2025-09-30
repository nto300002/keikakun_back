import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import func
import datetime

from app.models.welfare_recipient import (
    WelfareRecipient,
    ServiceRecipientDetail,
    EmergencyContact,
    DisabilityStatus,
    DisabilityDetail,
)
from app.models.enums import (
    GenderType,
    FormOfResidence,
    MeansOfTransportation,
    LivelihoodProtection,
    DisabilityCategory,
    ApplicationStatus,
    PhysicalDisabilityType,
)

pytestmark = pytest.mark.asyncio

async def test_create_welfare_recipient(db_session: AsyncSession):
    """WelfareRecipientの基本的な作成テスト"""
    recipient = WelfareRecipient(
        first_name="太郎",
        last_name="山田",
        first_name_furigana="たろう",
        last_name_furigana="やまだ",
        birth_day=datetime.date(1990, 1, 1),
        gender=GenderType.male,
    )
    db_session.add(recipient)
    await db_session.commit()
    await db_session.refresh(recipient)

    assert recipient.id is not None
    assert recipient.first_name == "太郎"
    assert recipient.gender == GenderType.male

async def test_full_recipient_creation(db_session: AsyncSession):
    """関連モデルを含むWelfareRecipientの完全な作成テスト"""

    # 1. WelfareRecipientを作成
    recipient = WelfareRecipient(
        first_name="花子",
        last_name="鈴木",
        first_name_furigana="はなこ",
        last_name_furigana="すずき",
        birth_day=datetime.date(1988, 4, 1),
        gender=GenderType.female,
    )

    # 2. ServiceRecipientDetailを作成し、関連付ける
    recipient.detail = ServiceRecipientDetail(
        address="東京都新宿区西新宿2-8-1",
        form_of_residence=FormOfResidence.home_alone,
        means_of_transportation=MeansOfTransportation.public_transport,
        tel="090-1234-5678",
    )

    # 3. EmergencyContactを複数作成し、関連付ける
    recipient.detail.emergency_contacts.extend([
        EmergencyContact(
            first_name="一郎", last_name="鈴木", first_name_furigana="いちろう", last_name_furigana="すずき",
            relationship="父", tel="080-1111-2222", priority=1
        ),
        EmergencyContact(
            first_name="春子", last_name="鈴木", first_name_furigana="はるこ", last_name_furigana="すずき",
            relationship="母", tel="080-3333-4444", priority=2
        ),
    ])

    # 4. DisabilityStatusを作成し、関連付ける
    recipient.disability_status = DisabilityStatus(
        disability_or_disease_name="統合失調症",
        livelihood_protection=LivelihoodProtection.not_receiving, 
        special_remarks="特になし",
    )

    # 5. DisabilityDetailを複数作成し、関連付ける
    recipient.disability_status.details.extend([
        DisabilityDetail(
            category=DisabilityCategory.mental_health_handbook,
            grade_or_level="2",
            application_status=ApplicationStatus.acquired,
        ),
        DisabilityDetail(
            category=DisabilityCategory.disability_basic_pension,
            grade_or_level="2",
            application_status=ApplicationStatus.acquired,
        ),
    ])

    db_session.add(recipient)
    await db_session.commit()
    await db_session.refresh(recipient)

    # --- 検証 ---
    stmt = select(WelfareRecipient).where(WelfareRecipient.id == recipient.id).options(
        selectinload(WelfareRecipient.detail).selectinload(ServiceRecipientDetail.emergency_contacts),
        selectinload(WelfareRecipient.disability_status).selectinload(DisabilityStatus.details)
    )
    result = await db_session.execute(stmt)
    retrieved_recipient = result.scalar_one()

    # 基本情報の検証
    assert retrieved_recipient.first_name == "花子"

    # ServiceRecipientDetailの検証
    assert retrieved_recipient.detail is not None
    assert retrieved_recipient.detail.address == "東京都新宿区西新宿2-8-1"
    assert retrieved_recipient.detail.form_of_residence == FormOfResidence.home_alone

    # EmergencyContactの検証
    assert len(retrieved_recipient.detail.emergency_contacts) == 2
    assert retrieved_recipient.detail.emergency_contacts[0].first_name == "一郎"
    assert retrieved_recipient.detail.emergency_contacts[1].priority == 2

    # DisabilityStatusの検証
    assert retrieved_recipient.disability_status is not None
    assert retrieved_recipient.disability_status.disability_or_disease_name == "統合失調症"

    # DisabilityDetailの検証
    assert len(retrieved_recipient.disability_status.details) == 2
    assert retrieved_recipient.disability_status.details[0].category == DisabilityCategory.mental_health_handbook
    assert retrieved_recipient.disability_status.details[1].grade_or_level == "2"

async def test_cascade_delete(db_session: AsyncSession):
    """WelfareRecipient削除時のカスケード削除テスト"""
    # テストデータ作成
    recipient = WelfareRecipient(
        first_name="削除", last_name="テスト", first_name_furigana="さくじょ", last_name_furigana="てすと",
        birth_day=datetime.date(2000, 1, 1), gender=GenderType.other
    )
    recipient.detail = ServiceRecipientDetail(address="a", form_of_residence=FormOfResidence.other, means_of_transportation=MeansOfTransportation.other, tel="d")
    recipient.detail.emergency_contacts.append(EmergencyContact(first_name="e", last_name="f", first_name_furigana="g", last_name_furigana="h", relationship="i", tel="j"))
    recipient.disability_status = DisabilityStatus(disability_or_disease_name="b", livelihood_protection=LivelihoodProtection.applying)
    recipient.disability_status.details.append(DisabilityDetail(category=DisabilityCategory.public_assistance, application_status=ApplicationStatus.applying))

    db_session.add(recipient)
    await db_session.commit()
    recipient_id = recipient.id
    detail_id = recipient.detail.id
    status_id = recipient.disability_status.id
    
    # 削除実行
    await db_session.delete(recipient)
    await db_session.commit()

    # 関連データが削除されたことを確認
    from sqlalchemy import select
    res = await db_session.execute(select(WelfareRecipient).filter_by(id=recipient_id))
    assert res.scalar_one_or_none() is None
    res = await db_session.execute(select(ServiceRecipientDetail).filter_by(id=detail_id))
    assert res.scalar_one_or_none() is None
    res = await db_session.execute(select(DisabilityStatus).filter_by(id=status_id))
    assert res.scalar_one_or_none() is None
    
    res = await db_session.execute(select(func.count(EmergencyContact.id)).filter(EmergencyContact.service_recipient_detail_id == detail_id))
    assert res.scalar() == 0
    res = await db_session.execute(select(func.count(DisabilityDetail.id)).filter(DisabilityDetail.disability_status_id == status_id))
    assert res.scalar() == 0
