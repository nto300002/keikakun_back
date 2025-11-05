import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import uuid4
from datetime import date
from fastapi import HTTPException

from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.assessment import (
    FamilyOfServiceRecipients,
    WelfareServicesUsed,
    MedicalMatters,
    HistoryOfHospitalVisits,
    EmploymentRelated,
    IssueAnalysis,
)
from app.models.enums import (
    StaffRole,
    OfficeType,
    GenderType,
    Household,
    MedicalCareInsurance,
    AidingType,
    WorkConditions,
    WorkOutsideFacility,
)
from app.core.security import get_password_hash

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def setup_staff_and_office(db_session: AsyncSession):
    """テスト用のスタッフと事業所を作成"""
    staff = Staff(
        first_name="管理者",
        last_name="テスト",
        full_name="テスト 管理者",
        email=f"test_admin_{uuid4()}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.owner,
    )
    db_session.add(staff)
    await db_session.flush()
    await db_session.refresh(staff)

    office = Office(
        name="テスト事業所",
        type=OfficeType.type_A_office,
        created_by=staff.id,
        last_modified_by=staff.id,
    )
    db_session.add(office)
    await db_session.flush()
    await db_session.refresh(office)

    # スタッフと事業所を関連付け
    association = OfficeStaff(
        staff_id=staff.id,
        office_id=office.id,
        is_primary=True
    )
    db_session.add(association)
    await db_session.flush()

    return staff, office


@pytest.fixture
async def setup_recipient(db_session: AsyncSession, setup_staff_and_office):
    """テスト用の利用者を作成"""
    staff, office = setup_staff_and_office

    recipient = WelfareRecipient(
        first_name="太郎",
        last_name="テスト",
        first_name_furigana="たろう",
        last_name_furigana="てすと",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male,
    )
    db_session.add(recipient)
    await db_session.flush()
    await db_session.refresh(recipient)

    # 事業所との関連付け
    office_recipient_association = OfficeWelfareRecipient(
        welfare_recipient_id=recipient.id,
        office_id=office.id
    )
    db_session.add(office_recipient_association)
    await db_session.flush()

    return recipient, staff, office


@pytest.fixture
async def setup_other_office_staff(db_session: AsyncSession):
    """別の事業所のスタッフを作成（権限テスト用）"""
    staff = Staff(
        first_name="スタッフ",
        last_name="別事業所",
        full_name="別事業所 スタッフ",
        email=f"other_staff_{uuid4()}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.employee,
    )
    db_session.add(staff)
    await db_session.flush()
    await db_session.refresh(staff)

    office = Office(
        name="別の事業所",
        type=OfficeType.type_B_office,
        created_by=staff.id,
        last_modified_by=staff.id,
    )
    db_session.add(office)
    await db_session.flush()
    await db_session.refresh(office)

    # スタッフと事業所を関連付け
    association = OfficeStaff(
        staff_id=staff.id,
        office_id=office.id,
        is_primary=True
    )
    db_session.add(association)
    await db_session.flush()

    return staff, office


class TestVerifyRecipientAccess:
    """権限検証（verify_recipient_access）のテスト"""

    async def test_access_granted_for_same_office_staff(
        self, db_session: AsyncSession, setup_recipient
    ):
        """正常系: 同じ事業所のスタッフはアクセス可能"""
        from app.services.assessment_service import verify_recipient_access

        recipient, staff, office = setup_recipient

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        # アクセス権限を検証（例外が発生しないことを確認）
        verified_recipient = await verify_recipient_access(
            db_session, recipient.id, staff
        )

        assert verified_recipient.id == recipient.id

    async def test_access_denied_for_different_office_staff(
        self, db_session: AsyncSession, setup_recipient, setup_other_office_staff
    ):
        """異常系: 異なる事業所のスタッフはアクセス拒否（403エラー）"""
        from app.services.assessment_service import verify_recipient_access

        recipient, _, _ = setup_recipient
        other_staff, _ = setup_other_office_staff

        # 別事業所スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == other_staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        other_staff = result.scalar_one()

        # 403エラーが発生することを確認
        with pytest.raises(HTTPException) as exc_info:
            await verify_recipient_access(db_session, recipient.id, other_staff)

        assert exc_info.value.status_code == 403
        assert "アクセスする権限がありません" in str(exc_info.value.detail)

    async def test_access_denied_for_nonexistent_recipient(
        self, db_session: AsyncSession, setup_staff_and_office
    ):
        """異常系: 存在しない利用者の場合、404エラー"""
        from app.services.assessment_service import verify_recipient_access

        staff, office = setup_staff_and_office

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        # 存在しないUUID
        nonexistent_recipient_id = uuid4()

        # 404エラーが発生することを確認
        with pytest.raises(HTTPException) as exc_info:
            await verify_recipient_access(db_session, nonexistent_recipient_id, staff)

        assert exc_info.value.status_code == 404
        assert "利用者が見つかりません" in str(exc_info.value.detail)


class TestGetAllAssessmentData:
    """全アセスメント情報取得のテスト"""

    async def test_get_all_data_with_empty_data(
        self, db_session: AsyncSession, setup_recipient
    ):
        """正常系: データが存在しない項目はNoneまたは空リスト"""
        from app.services.assessment_service import get_all_assessment_data

        recipient, staff, _ = setup_recipient

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        # 全アセスメント情報を取得
        assessment_data = await get_all_assessment_data(
            db_session, recipient.id, staff
        )

        # 各フィールドが空であることを確認
        assert assessment_data.family_members == []
        assert assessment_data.service_history == []
        assert assessment_data.medical_info is None
        assert assessment_data.hospital_visits == []
        assert assessment_data.employment is None
        assert assessment_data.issue_analysis is None

    async def test_get_all_data_with_full_data(
        self, db_session: AsyncSession, setup_recipient
    ):
        """正常系: 全データが正しく取得される"""
        from app.services.assessment_service import get_all_assessment_data

        recipient, staff, _ = setup_recipient

        # 家族構成を作成
        family_member = FamilyOfServiceRecipients(
            welfare_recipient_id=recipient.id,
            name="花子",
            relationship="母",
            household=Household.same,
            ones_health="良好",
        )
        db_session.add(family_member)

        # サービス利用歴を作成
        service_history = WelfareServicesUsed(
            welfare_recipient_id=recipient.id,
            office_name="ABC事業所",
            starting_day=date(2020, 4, 1),
            amount_used="月80時間",
            service_name="就労継続支援B型",
        )
        db_session.add(service_history)

        # 医療情報を作成
        medical_info = MedicalMatters(
            welfare_recipient_id=recipient.id,
            medical_care_insurance=MedicalCareInsurance.national_health_insurance,
            aiding=AidingType.subsidized,
            history_of_hospitalization_in_the_past_2_years=True,
        )
        db_session.add(medical_info)
        await db_session.flush()
        await db_session.refresh(medical_info)

        # 通院歴を作成
        hospital_visit = HistoryOfHospitalVisits(
            medical_matters_id=medical_info.id,
            disease="うつ病",
            frequency_of_hospital_visits="月1回",
            symptoms="気分の落ち込み",
            medical_institution="さくら病院",
            doctor="山田医師",
            tel="03-1234-5678",
            taking_medicine=True,
        )
        db_session.add(hospital_visit)

        # 就労関係を作成
        employment = EmploymentRelated(
            welfare_recipient_id=recipient.id,
            created_by_staff_id=staff.id,
            work_conditions=WorkConditions.continuous_support_b,
            regular_or_part_time_job=False,
            employment_support=True,
            work_experience_in_the_past_year=False,
            suspension_of_work=False,
            general_employment_request=True,
            work_outside_the_facility=WorkOutsideFacility.hope,
        )
        db_session.add(employment)

        # 課題分析を作成
        issue_analysis = IssueAnalysis(
            welfare_recipient_id=recipient.id,
            created_by_staff_id=staff.id,
            what_i_like_to_do="絵を描くこと",
            the_life_i_want="自立した生活",
        )
        db_session.add(issue_analysis)

        await db_session.flush()

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        # 全アセスメント情報を取得
        assessment_data = await get_all_assessment_data(
            db_session, recipient.id, staff
        )

        # 各フィールドが正しく取得されていることを確認
        assert len(assessment_data.family_members) == 1
        assert assessment_data.family_members[0].name == "花子"

        assert len(assessment_data.service_history) == 1
        assert assessment_data.service_history[0].office_name == "ABC事業所"

        assert assessment_data.medical_info is not None
        assert assessment_data.medical_info.medical_care_insurance == MedicalCareInsurance.national_health_insurance

        assert len(assessment_data.hospital_visits) == 1
        assert assessment_data.hospital_visits[0].disease == "うつ病"

        assert assessment_data.employment is not None
        assert assessment_data.employment.work_conditions == WorkConditions.continuous_support_b

        assert assessment_data.issue_analysis is not None
        assert assessment_data.issue_analysis.what_i_like_to_do == "絵を描くこと"

    async def test_access_denied_for_different_office(
        self, db_session: AsyncSession, setup_recipient, setup_other_office_staff
    ):
        """異常系: 権限がない場合、403エラー"""
        from app.services.assessment_service import get_all_assessment_data

        recipient, _, _ = setup_recipient
        other_staff, _ = setup_other_office_staff

        # 別事業所スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == other_staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        other_staff = result.scalar_one()

        # 403エラーが発生することを確認
        with pytest.raises(HTTPException) as exc_info:
            await get_all_assessment_data(db_session, recipient.id, other_staff)

        assert exc_info.value.status_code == 403


class TestFamilyMemberServices:
    """家族構成のサービス層テスト"""

    async def test_create_family_member_with_validation(
        self, db_session: AsyncSession, setup_recipient
    ):
        """正常系: 家族メンバーを作成"""
        from app.services.assessment_service import create_family_member_with_validation
        from app.schemas.assessment import FamilyMemberCreate

        recipient, staff, _ = setup_recipient

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        # 家族メンバー作成データ
        member_data = FamilyMemberCreate(
            name="田中太郎",
            relationship="父",
            household=Household.same,
            ones_health="良好"
        )

        # 家族メンバーを作成
        created_member = await create_family_member_with_validation(
            db_session, recipient.id, member_data, staff
        )

        assert created_member.id is not None
        assert created_member.name == "田中太郎"
        assert created_member.relationship == "父"
        assert created_member.welfare_recipient_id == recipient.id

    async def test_create_family_member_access_denied(
        self, db_session: AsyncSession, setup_recipient, setup_other_office_staff
    ):
        """異常系: 権限がない場合、403エラー"""
        from app.services.assessment_service import create_family_member_with_validation
        from app.schemas.assessment import FamilyMemberCreate

        recipient, _, _ = setup_recipient
        other_staff, _ = setup_other_office_staff

        # 別事業所スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == other_staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        other_staff = result.scalar_one()

        member_data = FamilyMemberCreate(
            name="田中太郎",
            relationship="父",
            household=Household.same,
            ones_health="良好"
        )

        # 403エラーが発生することを確認
        with pytest.raises(HTTPException) as exc_info:
            await create_family_member_with_validation(
                db_session, recipient.id, member_data, other_staff
            )

        assert exc_info.value.status_code == 403

    async def test_update_family_member_with_validation(
        self, db_session: AsyncSession, setup_recipient
    ):
        """正常系: 家族メンバーを更新"""
        from app.services.assessment_service import (
            create_family_member_with_validation,
            update_family_member_with_validation
        )
        from app.schemas.assessment import FamilyMemberCreate, FamilyMemberUpdate

        recipient, staff, _ = setup_recipient

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        # 家族メンバーを作成
        member_data = FamilyMemberCreate(
            name="田中太郎",
            relationship="父",
            household=Household.same,
            ones_health="良好"
        )
        created_member = await create_family_member_with_validation(
            db_session, recipient.id, member_data, staff
        )

        # 家族メンバーを更新
        update_data = FamilyMemberUpdate(
            name="田中次郎",
            ones_health="やや不良"
        )
        updated_member = await update_family_member_with_validation(
            db_session, created_member.id, update_data, staff
        )

        assert updated_member.name == "田中次郎"
        assert updated_member.ones_health == "やや不良"
        assert updated_member.relationship == "父"  # 変更されていない

    async def test_update_family_member_not_found(
        self, db_session: AsyncSession, setup_recipient
    ):
        """異常系: 存在しない家族メンバーの場合、404エラー"""
        from app.services.assessment_service import update_family_member_with_validation
        from app.schemas.assessment import FamilyMemberUpdate

        recipient, staff, _ = setup_recipient

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        update_data = FamilyMemberUpdate(name="田中次郎")

        # 404エラーが発生することを確認
        with pytest.raises(HTTPException) as exc_info:
            await update_family_member_with_validation(
                db_session, 99999, update_data, staff
            )

        assert exc_info.value.status_code == 404

    async def test_delete_family_member_with_validation(
        self, db_session: AsyncSession, setup_recipient
    ):
        """正常系: 家族メンバーを削除"""
        from app.services.assessment_service import (
            create_family_member_with_validation,
            delete_family_member_with_validation
        )
        from app.schemas.assessment import FamilyMemberCreate

        recipient, staff, _ = setup_recipient

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        # 家族メンバーを作成
        member_data = FamilyMemberCreate(
            name="田中太郎",
            relationship="父",
            household=Household.same,
            ones_health="良好"
        )
        created_member = await create_family_member_with_validation(
            db_session, recipient.id, member_data, staff
        )

        # 家族メンバーを削除
        await delete_family_member_with_validation(
            db_session, created_member.id, staff
        )

        # 削除されたことを確認
        from app.crud.crud_family_member import crud_family_member
        family_members = await crud_family_member.get_family_members(
            db_session, recipient_id=recipient.id
        )
        assert len(family_members) == 0


class TestMedicalInfoServices:
    """医療基本情報のサービス層テスト"""

    async def test_upsert_medical_info_create(
        self, db_session: AsyncSession, setup_recipient
    ):
        """正常系: 医療基本情報を作成（存在しない場合）"""
        from app.services.assessment_service import upsert_medical_info_with_validation
        from app.schemas.assessment import MedicalInfoCreate

        recipient, staff, _ = setup_recipient

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        # 医療情報作成データ
        medical_data = MedicalInfoCreate(
            medical_care_insurance=MedicalCareInsurance.national_health_insurance,
            aiding=AidingType.subsidized,
            history_of_hospitalization_in_the_past_2_years=True
        )

        # 医療情報を作成
        created_info = await upsert_medical_info_with_validation(
            db_session, recipient.id, medical_data, staff
        )

        assert created_info.id is not None
        assert created_info.medical_care_insurance == MedicalCareInsurance.national_health_insurance
        assert created_info.welfare_recipient_id == recipient.id

    async def test_upsert_medical_info_update(
        self, db_session: AsyncSession, setup_recipient
    ):
        """正常系: 医療基本情報を更新（存在する場合）"""
        from app.services.assessment_service import upsert_medical_info_with_validation
        from app.schemas.assessment import MedicalInfoCreate

        recipient, staff, _ = setup_recipient

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        # 初回作成
        medical_data1 = MedicalInfoCreate(
            medical_care_insurance=MedicalCareInsurance.national_health_insurance,
            aiding=AidingType.none,
            history_of_hospitalization_in_the_past_2_years=False
        )
        await upsert_medical_info_with_validation(
            db_session, recipient.id, medical_data1, staff
        )

        # 更新
        medical_data2 = MedicalInfoCreate(
            medical_care_insurance=MedicalCareInsurance.social_insurance,
            aiding=AidingType.full_exemption,
            history_of_hospitalization_in_the_past_2_years=True
        )
        updated_info = await upsert_medical_info_with_validation(
            db_session, recipient.id, medical_data2, staff
        )

        assert updated_info.medical_care_insurance == MedicalCareInsurance.social_insurance
        assert updated_info.aiding == AidingType.full_exemption


class TestEmploymentServices:
    """就労関係のサービス層テスト"""

    async def test_upsert_employment_create_with_staff_id(
        self, db_session: AsyncSession, setup_recipient
    ):
        """正常系: 就労情報を作成（created_by_staff_idが設定される）"""
        from app.services.assessment_service import upsert_employment_with_validation
        from app.schemas.assessment import EmploymentCreate

        recipient, staff, _ = setup_recipient

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        # 就労情報作成データ
        employment_data = EmploymentCreate(
            work_conditions=WorkConditions.general_employment,
            regular_or_part_time_job=True,
            employment_support=False,
            work_experience_in_the_past_year=True,
            suspension_of_work=False,
            general_employment_request=True,
            work_outside_the_facility=WorkOutsideFacility.hope
        )

        # 就労情報を作成
        created_employment = await upsert_employment_with_validation(
            db_session, recipient.id, employment_data, staff
        )

        assert created_employment.id is not None
        assert created_employment.created_by_staff_id == staff.id
        assert created_employment.work_conditions == WorkConditions.general_employment

    async def test_upsert_employment_update_preserves_staff_id(
        self, db_session: AsyncSession, setup_recipient, setup_other_office_staff
    ):
        """正常系: 就労情報を更新（created_by_staff_idは変更されない）"""
        from app.services.assessment_service import upsert_employment_with_validation
        from app.schemas.assessment import EmploymentCreate

        recipient, staff1, _ = setup_recipient

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff1.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff1 = result.scalar_one()

        # 初回作成
        employment_data1 = EmploymentCreate(
            work_conditions=WorkConditions.part_time,
            regular_or_part_time_job=False,
            employment_support=True,
            work_experience_in_the_past_year=False,
            suspension_of_work=False,
            general_employment_request=False,
            work_outside_the_facility=WorkOutsideFacility.not_hope
        )
        initial_employment = await upsert_employment_with_validation(
            db_session, recipient.id, employment_data1, staff1
        )

        # 更新（同じスタッフで）
        employment_data2 = EmploymentCreate(
            work_conditions=WorkConditions.general_employment,
            regular_or_part_time_job=True,
            employment_support=False,
            work_experience_in_the_past_year=True,
            suspension_of_work=False,
            general_employment_request=True,
            work_outside_the_facility=WorkOutsideFacility.hope
        )
        updated_employment = await upsert_employment_with_validation(
            db_session, recipient.id, employment_data2, staff1
        )

        # created_by_staff_idは最初のスタッフIDのまま
        assert updated_employment.created_by_staff_id == staff1.id
        assert updated_employment.work_conditions == WorkConditions.general_employment


class TestIssueAnalysisServices:
    """課題分析のサービス層テスト"""

    async def test_upsert_issue_analysis_create(
        self, db_session: AsyncSession, setup_recipient
    ):
        """正常系: 課題分析を作成（created_by_staff_idが設定される）"""
        from app.services.assessment_service import upsert_issue_analysis_with_validation
        from app.schemas.assessment import IssueAnalysisCreate

        recipient, staff, _ = setup_recipient

        # スタッフのoffice_associationsを事前にロード
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        staff = result.scalar_one()

        # 課題分析作成データ
        analysis_data = IssueAnalysisCreate(
            what_i_like_to_do="絵を描くこと",
            im_not_good_at="人前で話すこと",
            the_life_i_want="自立した生活",
            future_dreams="アーティストになること"
        )

        # 課題分析を作成
        created_analysis = await upsert_issue_analysis_with_validation(
            db_session, recipient.id, analysis_data, staff
        )

        assert created_analysis.id is not None
        assert created_analysis.created_by_staff_id == staff.id
        assert created_analysis.what_i_like_to_do == "絵を描くこと"
