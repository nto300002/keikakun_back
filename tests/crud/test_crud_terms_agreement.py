"""
TermsAgreement (利用規約同意履歴) CRUDのテスト
TDD方式でテストを先に作成
"""
from sqlalchemy.ext.asyncio import AsyncSession
import pytest
from datetime import datetime, timezone

from app import crud
from app.schemas.terms_agreement import TermsAgreementCreate, TermsAgreementUpdate

pytestmark = pytest.mark.asyncio


async def test_create_terms_agreement(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    利用規約同意履歴作成テスト
    """
    staff = await employee_user_factory()

    # 同意履歴データ
    agreement_data = TermsAgreementCreate(
        staff_id=staff.id,
        terms_version="1.0",
        privacy_version="1.0",
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    )

    created_agreement = await crud.terms_agreement.create(
        db=db_session,
        obj_in=agreement_data
    )

    assert created_agreement.id is not None
    assert created_agreement.staff_id == staff.id
    assert created_agreement.terms_version == "1.0"
    assert created_agreement.privacy_version == "1.0"
    assert created_agreement.ip_address == "192.168.1.1"
    assert created_agreement.user_agent == "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    assert created_agreement.terms_of_service_agreed_at is None
    assert created_agreement.privacy_policy_agreed_at is None


async def test_get_by_staff_id(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    スタッフIDで同意履歴を取得するテスト（1:1関係）
    """
    staff = await employee_user_factory()

    agreement_data = TermsAgreementCreate(
        staff_id=staff.id,
        terms_version="1.0",
        privacy_version="1.0"
    )

    created_agreement = await crud.terms_agreement.create(
        db=db_session,
        obj_in=agreement_data
    )

    # スタッフIDで取得
    retrieved_agreement = await crud.terms_agreement.get_by_staff_id(
        db=db_session,
        staff_id=staff.id
    )

    assert retrieved_agreement is not None
    assert retrieved_agreement.id == created_agreement.id
    assert retrieved_agreement.staff_id == staff.id


async def test_get_by_staff_id_not_found(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    存在しないスタッフIDで取得するとNoneが返ることをテスト
    """
    import uuid

    non_existent_staff_id = uuid.uuid4()

    retrieved_agreement = await crud.terms_agreement.get_by_staff_id(
        db=db_session,
        staff_id=non_existent_staff_id
    )

    assert retrieved_agreement is None


async def test_update_agreement(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    同意履歴の更新テスト
    """
    staff = await employee_user_factory()

    # 作成
    agreement_data = TermsAgreementCreate(
        staff_id=staff.id,
        terms_version="1.0",
        privacy_version="1.0"
    )

    created_agreement = await crud.terms_agreement.create(
        db=db_session,
        obj_in=agreement_data
    )

    # 更新データ
    now = datetime.now(timezone.utc)
    update_data = TermsAgreementUpdate(
        terms_of_service_agreed_at=now,
        privacy_policy_agreed_at=now,
        terms_version="1.1",
        privacy_version="1.1",
        ip_address="10.0.0.1",
        user_agent="Updated User Agent"
    )

    # 更新
    updated_agreement = await crud.terms_agreement.update(
        db=db_session,
        db_obj=created_agreement,
        obj_in=update_data
    )

    assert updated_agreement.id == created_agreement.id
    assert updated_agreement.terms_of_service_agreed_at is not None
    assert updated_agreement.privacy_policy_agreed_at is not None
    assert updated_agreement.terms_version == "1.1"
    assert updated_agreement.privacy_version == "1.1"
    assert updated_agreement.ip_address == "10.0.0.1"
    assert updated_agreement.user_agent == "Updated User Agent"


async def test_agree_to_terms_new_record(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    新規スタッフの同意記録テスト（レコードが存在しない場合）
    """
    staff = await employee_user_factory()

    # 同意を記録
    agreement = await crud.terms_agreement.agree_to_terms(
        db=db_session,
        staff_id=staff.id,
        terms_version="1.0",
        privacy_version="1.0",
        ip_address="192.168.1.1",
        user_agent="Test User Agent"
    )

    assert agreement.id is not None
    assert agreement.staff_id == staff.id
    assert agreement.terms_of_service_agreed_at is not None
    assert agreement.privacy_policy_agreed_at is not None
    assert agreement.terms_version == "1.0"
    assert agreement.privacy_version == "1.0"
    assert agreement.ip_address == "192.168.1.1"
    assert agreement.user_agent == "Test User Agent"


async def test_agree_to_terms_update_existing(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    既存の同意履歴を更新するテスト
    """
    staff = await employee_user_factory()

    # 既存レコードを作成
    existing_data = TermsAgreementCreate(
        staff_id=staff.id,
        terms_version="1.0",
        privacy_version="1.0"
    )
    await crud.terms_agreement.create(db=db_session, obj_in=existing_data)

    # 新しいバージョンに同意
    updated_agreement = await crud.terms_agreement.agree_to_terms(
        db=db_session,
        staff_id=staff.id,
        terms_version="2.0",
        privacy_version="2.0",
        ip_address="10.0.0.1",
        user_agent="Updated User Agent"
    )

    assert updated_agreement.staff_id == staff.id
    assert updated_agreement.terms_of_service_agreed_at is not None
    assert updated_agreement.privacy_policy_agreed_at is not None
    assert updated_agreement.terms_version == "2.0"
    assert updated_agreement.privacy_version == "2.0"
    assert updated_agreement.ip_address == "10.0.0.1"

    # レコードが1つだけであることを確認（1:1関係）
    retrieved = await crud.terms_agreement.get_by_staff_id(
        db=db_session,
        staff_id=staff.id
    )
    assert retrieved.id == updated_agreement.id


async def test_agree_to_terms_without_optional_params(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    IPアドレスやユーザーエージェントなしで同意を記録できることをテスト
    """
    staff = await employee_user_factory()

    agreement = await crud.terms_agreement.agree_to_terms(
        db=db_session,
        staff_id=staff.id,
        terms_version="1.0",
        privacy_version="1.0"
    )

    assert agreement.id is not None
    assert agreement.staff_id == staff.id
    assert agreement.terms_of_service_agreed_at is not None
    assert agreement.privacy_policy_agreed_at is not None
    assert agreement.ip_address is None
    assert agreement.user_agent is None


async def test_one_to_one_relationship(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    1:1関係が正しく維持されることをテスト
    同じスタッフに対して複数のレコードが作成されないことを確認
    """
    staff = await employee_user_factory()

    # 1回目の同意
    first_agreement = await crud.terms_agreement.agree_to_terms(
        db=db_session,
        staff_id=staff.id,
        terms_version="1.0",
        privacy_version="1.0"
    )

    first_id = first_agreement.id

    # 2回目の同意（既存レコードを更新）
    second_agreement = await crud.terms_agreement.agree_to_terms(
        db=db_session,
        staff_id=staff.id,
        terms_version="2.0",
        privacy_version="2.0"
    )

    # IDが同じ（更新されている）
    assert second_agreement.id == first_id
    assert second_agreement.terms_version == "2.0"

    # レコード数が1つであることを確認
    retrieved = await crud.terms_agreement.get_by_staff_id(
        db=db_session,
        staff_id=staff.id
    )
    assert retrieved.id == first_id


async def test_partial_update(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    部分的な更新が正しく動作することをテスト
    """
    staff = await employee_user_factory()

    # 作成
    agreement_data = TermsAgreementCreate(
        staff_id=staff.id,
        terms_version="1.0",
        privacy_version="1.0",
        ip_address="192.168.1.1"
    )

    created_agreement = await crud.terms_agreement.create(
        db=db_session,
        obj_in=agreement_data
    )

    # 利用規約のみ更新
    now = datetime.now(timezone.utc)
    update_data = TermsAgreementUpdate(
        terms_of_service_agreed_at=now,
        terms_version="2.0"
    )

    updated_agreement = await crud.terms_agreement.update(
        db=db_session,
        db_obj=created_agreement,
        obj_in=update_data
    )

    assert updated_agreement.terms_of_service_agreed_at is not None
    assert updated_agreement.terms_version == "2.0"
    # プライバシーポリシーは変更されていない
    assert updated_agreement.privacy_policy_agreed_at is None
    assert updated_agreement.privacy_version == "1.0"
    # IPアドレスも変更されていない
    assert updated_agreement.ip_address == "192.168.1.1"
