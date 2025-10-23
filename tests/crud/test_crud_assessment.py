"""
アセスメントシート機能のCRUD層テスト

TDD (テスト駆動開発) アプローチに基づき、
CRUD実装前にテストを作成します。
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
import uuid

from app.models.enums import (
    Household,
    MedicalCareInsurance,
    AidingType,
    WorkConditions,
    WorkOutsideFacility,
    GenderType,
)
from app.schemas.assessment import (
    FamilyMemberCreate,
    FamilyMemberUpdate,
    ServiceHistoryCreate,
    ServiceHistoryUpdate,
    MedicalInfoCreate,
    MedicalInfoUpdate,
    HospitalVisitCreate,
    HospitalVisitUpdate,
    EmploymentCreate,
    EmploymentUpdate,
    IssueAnalysisCreate,
    IssueAnalysisUpdate,
)

pytestmark = pytest.mark.asyncio


# =============================================================================
# フィクスチャ: アセスメントテスト用のシンプルな利用者
# =============================================================================

@pytest_asyncio.fixture
async def simple_welfare_recipient(
    db_session: AsyncSession,
    employee_user_factory,
    office_factory
):
    """アセスメントテスト用のシンプルな利用者フィクスチャ（カレンダーなし）"""
    from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
    from app.models.enums import GenderType
    from datetime import date

    # スタッフと事業所を作成
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    if not office:
        office = await office_factory(creator=staff, session=db_session)

    # 利用者を作成
    recipient = WelfareRecipient(
        last_name="テスト",
        first_name="太郎",
        last_name_furigana="テスト",
        first_name_furigana="タロウ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male
    )

    db_session.add(recipient)
    await db_session.flush()

    # 事業所との関連付けを作成
    office_recipient_association = OfficeWelfareRecipient(
        welfare_recipient_id=recipient.id,
        office_id=office.id
    )
    db_session.add(office_recipient_association)
    await db_session.flush()
    await db_session.refresh(recipient)

    # テストで使いやすいように、office_idを属性として追加
    recipient.office_id = office.id

    return recipient


# =============================================================================
# 1. 家族構成CRUDのテスト
# =============================================================================

class TestFamilyMemberCRUD:
    """家族構成CRUDのテストクラス"""

    async def test_get_family_members(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """get_family_members: 指定された利用者の家族構成を全て取得"""
        from app.crud.crud_family_member import crud_family_member

        recipient_id = simple_welfare_recipient.id

        # 家族メンバーを作成
        member1_data = FamilyMemberCreate(
            name="山田太郎",
            relationship="父",
            household=Household.same,
            ones_health="良好"
        )
        member2_data = FamilyMemberCreate(
            name="山田花子",
            relationship="母",
            household=Household.same,
            ones_health="良好"
        )

        await crud_family_member.create(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=member1_data
        )
        await crud_family_member.create(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=member2_data
        )

        # 取得
        family_members = await crud_family_member.get_family_members(
            db=db_session,
            recipient_id=recipient_id
        )

        assert len(family_members) == 2
        assert family_members[0].name == "山田太郎"
        assert family_members[1].name == "山田花子"


    async def test_get_family_members_empty(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """get_family_members: 該当データがない場合、空リストを返す"""
        from app.crud.crud_family_member import crud_family_member

        recipient_id = simple_welfare_recipient.id

        family_members = await crud_family_member.get_family_members(
            db=db_session,
            recipient_id=recipient_id
        )

        assert family_members == []


    async def test_create_family_member(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """create_family_member: 新しい家族メンバーを作成"""
        from app.crud.crud_family_member import crud_family_member

        recipient_id = simple_welfare_recipient.id

        member_data = FamilyMemberCreate(
            name="山田太郎",
            relationship="父",
            household=Household.same,
            ones_health="良好",
            remarks="特になし"
        )

        created_member = await crud_family_member.create(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=member_data
        )

        assert created_member.id is not None
        assert created_member.name == "山田太郎"
        assert created_member.relationship == "父"
        assert created_member.welfare_recipient_id == recipient_id


    async def test_update_family_member(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """update_family_member: 既存の家族メンバーを更新"""
        from app.crud.crud_family_member import crud_family_member

        recipient_id = simple_welfare_recipient.id

        # 作成
        member_data = FamilyMemberCreate(
            name="山田太郎",
            relationship="父",
            household=Household.same,
            ones_health="良好"
        )
        created_member = await crud_family_member.create(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=member_data
        )

        # 更新
        update_data = FamilyMemberUpdate(
            name="山田次郎",
            ones_health="やや不良"
        )
        updated_member = await crud_family_member.update(
            db=db_session,
            family_member_id=created_member.id,
            obj_in=update_data
        )

        assert updated_member is not None
        assert updated_member.name == "山田次郎"
        assert updated_member.ones_health == "やや不良"
        assert updated_member.relationship == "父"  # 変更されていない


    async def test_update_family_member_not_found(
        self,
        db_session: AsyncSession
    ):
        """update_family_member: 存在しないIDの場合、Noneを返す"""
        from app.crud.crud_family_member import crud_family_member

        update_data = FamilyMemberUpdate(name="新しい名前")

        updated_member = await crud_family_member.update(
            db=db_session,
            family_member_id=99999,  # 存在しないID
            obj_in=update_data
        )

        assert updated_member is None


    async def test_delete_family_member(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """delete_family_member: 既存の家族メンバーを削除"""
        from app.crud.crud_family_member import crud_family_member

        recipient_id = simple_welfare_recipient.id

        # 作成
        member_data = FamilyMemberCreate(
            name="山田太郎",
            relationship="父",
            household=Household.same,
            ones_health="良好"
        )
        created_member = await crud_family_member.create(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=member_data
        )

        # 削除
        result = await crud_family_member.delete(
            db=db_session,
            family_member_id=created_member.id
        )

        assert result is True

        # 削除されたことを確認
        family_members = await crud_family_member.get_family_members(
            db=db_session,
            recipient_id=recipient_id
        )
        assert len(family_members) == 0

    async def test_delete_family_member_not_found(
        self,
        db_session: AsyncSession
    ):
        """delete_family_member: 存在しないIDの場合、Falseを返す"""
        from app.crud.crud_family_member import crud_family_member

        result = await crud_family_member.delete(
            db=db_session,
            family_member_id=99999  # 存在しないID
        )

        assert result is False


# =============================================================================
# 2. 福祉サービス利用歴CRUDのテスト
# =============================================================================

class TestServiceHistoryCRUD:
    """福祉サービス利用歴CRUDのテストクラス"""

    async def test_get_service_history_sorted(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """get_service_history: 利用開始日の降順でソートされること"""
        from app.crud.crud_service_history import crud_service_history

        recipient_id = simple_welfare_recipient.id

        # 複数のサービス利用歴を作成（日付順序をバラバラに）
        history1 = ServiceHistoryCreate(
            office_name="事業所A",
            starting_day=date(2020, 1, 1),
            amount_used="週5日",
            service_name="就労継続支援B型"
        )
        history2 = ServiceHistoryCreate(
            office_name="事業所B",
            starting_day=date(2023, 1, 1),  # 最新
            amount_used="週3日",
            service_name="就労移行支援"
        )
        history3 = ServiceHistoryCreate(
            office_name="事業所C",
            starting_day=date(2021, 6, 1),
            amount_used="週4日",
            service_name="就労継続支援A型"
        )

        await crud_service_history.create(db=db_session, recipient_id=recipient_id, obj_in=history1)
        await crud_service_history.create(db=db_session, recipient_id=recipient_id, obj_in=history2)
        await crud_service_history.create(db=db_session, recipient_id=recipient_id, obj_in=history3)

        # 取得
        histories = await crud_service_history.get_service_history(
            db=db_session,
            recipient_id=recipient_id
        )

        assert len(histories) == 3
        # 降順（新しい順）でソートされていることを確認
        assert histories[0].office_name == "事業所B"  # 2023
        assert histories[1].office_name == "事業所C"  # 2021
        assert histories[2].office_name == "事業所A"  # 2020


# =============================================================================
# 3. 医療基本情報CRUDのテスト
# =============================================================================

class TestMedicalInfoCRUD:
    """医療基本情報CRUDのテストクラス"""

    async def test_get_medical_info(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """get_medical_info: 1対1の関係で取得"""
        from app.crud.crud_medical_info import crud_medical_info

        recipient_id = simple_welfare_recipient.id

        # 作成
        medical_data = MedicalInfoCreate(
            medical_care_insurance=MedicalCareInsurance.national_health_insurance,
            aiding=AidingType.none,
            history_of_hospitalization_in_the_past_2_years=False
        )
        await crud_medical_info.create(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=medical_data
        )

        # 取得
        medical_info = await crud_medical_info.get_medical_info(
            db=db_session,
            recipient_id=recipient_id
        )

        assert medical_info is not None
        assert medical_info.medical_care_insurance == MedicalCareInsurance.national_health_insurance
        assert medical_info.welfare_recipient_id == recipient_id

  
    async def test_get_medical_info_not_exists(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """get_medical_info: 存在しない場合、Noneを返す"""
        from app.crud.crud_medical_info import crud_medical_info

        recipient_id = simple_welfare_recipient.id

        medical_info = await crud_medical_info.get_medical_info(
            db=db_session,
            recipient_id=recipient_id
        )

        assert medical_info is None

    async def test_upsert_medical_info_create(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """upsert_medical_info: 存在しない場合は作成"""
        from app.crud.crud_medical_info import crud_medical_info

        recipient_id = simple_welfare_recipient.id

        medical_data = MedicalInfoCreate(
            medical_care_insurance=MedicalCareInsurance.social_insurance,
            aiding=AidingType.subsidized,
            history_of_hospitalization_in_the_past_2_years=True
        )

        medical_info = await crud_medical_info.upsert(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=medical_data
        )

        assert medical_info is not None
        assert medical_info.medical_care_insurance == MedicalCareInsurance.social_insurance
        assert medical_info.welfare_recipient_id == recipient_id

    async def test_upsert_medical_info_update(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """upsert_medical_info: 存在する場合は更新"""
        from app.crud.crud_medical_info import crud_medical_info

        recipient_id = simple_welfare_recipient.id

        # 初回作成
        medical_data1 = MedicalInfoCreate(
            medical_care_insurance=MedicalCareInsurance.national_health_insurance,
            aiding=AidingType.none,
            history_of_hospitalization_in_the_past_2_years=False
        )
        await crud_medical_info.upsert(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=medical_data1
        )

        # 更新
        medical_data2 = MedicalInfoCreate(
            medical_care_insurance=MedicalCareInsurance.social_insurance,
            aiding=AidingType.full_exemption,
            history_of_hospitalization_in_the_past_2_years=True
        )
        updated_info = await crud_medical_info.upsert(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=medical_data2
        )

        assert updated_info.medical_care_insurance == MedicalCareInsurance.social_insurance
        assert updated_info.aiding == AidingType.full_exemption
        assert updated_info.history_of_hospitalization_in_the_past_2_years is True

        # 1つしか存在しないことを確認
        medical_info = await crud_medical_info.get_medical_info(
            db=db_session,
            recipient_id=recipient_id
        )
        assert medical_info.id == updated_info.id


# =============================================================================
# 4. 通院歴CRUDのテスト
# =============================================================================

class TestHospitalVisitCRUD:
    """通院歴CRUDのテストクラス"""

    async def test_get_hospital_visits_with_join(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """get_hospital_visits: JOINが正しく動作"""
        from app.crud.crud_hospital_visit import crud_hospital_visit
        from app.crud.crud_medical_info import crud_medical_info

        recipient_id = simple_welfare_recipient.id

        # 医療基本情報を先に作成
        medical_data = MedicalInfoCreate(
            medical_care_insurance=MedicalCareInsurance.national_health_insurance,
            aiding=AidingType.none,
            history_of_hospitalization_in_the_past_2_years=False
        )
        await crud_medical_info.create(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=medical_data
        )

        # 通院歴を作成
        visit_data = HospitalVisitCreate(
            disease="糖尿病",
            frequency_of_hospital_visits="月1回",
            symptoms="特になし",
            medical_institution="〇〇病院",
            doctor="田中医師",
            tel="03-1234-5678",
            taking_medicine=True
        )
        await crud_hospital_visit.create(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=visit_data
        )

        # 取得（JOINして取得）
        visits = await crud_hospital_visit.get_hospital_visits(
            db=db_session,
            recipient_id=recipient_id
        )

        assert len(visits) == 1
        assert visits[0].disease == "糖尿病"

    async def test_create_hospital_visit_auto_create_medical_info(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient
    ):
        """create_hospital_visit: 医療基本情報が存在しない場合、先に作成される"""
        from app.crud.crud_hospital_visit import crud_hospital_visit

        recipient_id = simple_welfare_recipient.id

        visit_data = HospitalVisitCreate(
            disease="高血圧",
            frequency_of_hospital_visits="月1回",
            symptoms="軽度",
            medical_institution="△△クリニック",
            doctor="佐藤医師",
            tel="03-9876-5432",
            taking_medicine=True
        )

        created_visit = await crud_hospital_visit.create(
            db=db_session,
            recipient_id=recipient_id,
            obj_in=visit_data
        )

        assert created_visit is not None
        assert created_visit.disease == "高血圧"
        assert created_visit.medical_matters_id is not None


# =============================================================================
# 5. 就労関係CRUDのテスト
# =============================================================================

class TestEmploymentCRUD:
    """就労関係CRUDのテストクラス"""

    async def test_upsert_employment_create_with_staff_id(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient,
        employee_user_factory
    ):
        """upsert_employment: 新規作成時にcreated_by_staff_idが設定される"""
        from app.crud.crud_employment import crud_employment

        recipient_id = simple_welfare_recipient.id
        staff = await employee_user_factory()

        employment_data = EmploymentCreate(
            work_conditions=WorkConditions.general_employment,
            regular_or_part_time_job=True,
            employment_support=False,
            work_experience_in_the_past_year=True,
            suspension_of_work=False,
            general_employment_request=True,
            work_outside_the_facility=WorkOutsideFacility.hope
        )

        employment = await crud_employment.upsert(
            db=db_session,
            recipient_id=recipient_id,
            staff_id=staff.id,
            obj_in=employment_data
        )

        assert employment is not None
        assert employment.created_by_staff_id == staff.id
        assert employment.work_conditions == WorkConditions.general_employment

    async def test_upsert_employment_update_preserves_staff_id(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient,
        employee_user_factory
    ):
        """upsert_employment: 更新時にcreated_by_staff_idは変更されない"""
        from app.crud.crud_employment import crud_employment

        recipient_id = simple_welfare_recipient.id
        staff1 = await employee_user_factory()
        staff2 = await employee_user_factory()

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
        await crud_employment.upsert(
            db=db_session,
            recipient_id=recipient_id,
            staff_id=staff1.id,
            obj_in=employment_data1
        )

        # 別のスタッフで更新
        employment_data2 = EmploymentCreate(
            work_conditions=WorkConditions.general_employment,
            regular_or_part_time_job=True,
            employment_support=False,
            work_experience_in_the_past_year=True,
            suspension_of_work=False,
            general_employment_request=True,
            work_outside_the_facility=WorkOutsideFacility.hope
        )
        updated_employment = await crud_employment.upsert(
            db=db_session,
            recipient_id=recipient_id,
            staff_id=staff2.id,  # 別のスタッフID
            obj_in=employment_data2
        )

        # created_by_staff_idは最初のスタッフIDのまま
        assert updated_employment.created_by_staff_id == staff1.id
        assert updated_employment.work_conditions == WorkConditions.general_employment


# =============================================================================
# 6. 課題分析CRUDのテスト
# =============================================================================

class TestIssueAnalysisCRUD:
    """課題分析CRUDのテストクラス"""

    async def test_upsert_issue_analysis_create(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient,
        employee_user_factory
    ):
        """upsert_issue_analysis: 新規作成時にcreated_by_staff_idが設定される"""
        from app.crud.crud_issue_analysis import crud_issue_analysis

        recipient_id = simple_welfare_recipient.id
        staff = await employee_user_factory()

        analysis_data = IssueAnalysisCreate(
            what_i_like_to_do="絵を描くこと",
            im_not_good_at="人前で話すこと",
            the_life_i_want="自立した生活",
            future_dreams="アーティストになること"
        )

        analysis = await crud_issue_analysis.upsert(
            db=db_session,
            recipient_id=recipient_id,
            staff_id=staff.id,
            obj_in=analysis_data
        )

        assert analysis is not None
        assert analysis.created_by_staff_id == staff.id
        assert analysis.what_i_like_to_do == "絵を描くこと"


    async def test_upsert_issue_analysis_update_preserves_staff_id(
        self,
        db_session: AsyncSession,
        simple_welfare_recipient,
        employee_user_factory
    ):
        """upsert_issue_analysis: 更新時にcreated_by_staff_idは変更されない"""
        from app.crud.crud_issue_analysis import crud_issue_analysis

        recipient_id = simple_welfare_recipient.id
        staff1 = await employee_user_factory()
        staff2 = await employee_user_factory()

        # 初回作成
        analysis_data1 = IssueAnalysisCreate(
            what_i_like_to_do="音楽を聴くこと"
        )
        await crud_issue_analysis.upsert(
            db=db_session,
            recipient_id=recipient_id,
            staff_id=staff1.id,
            obj_in=analysis_data1
        )

        # 別のスタッフで更新
        analysis_data2 = IssueAnalysisCreate(
            what_i_like_to_do="料理を作ること",
            future_dreams="シェフになること"
        )
        updated_analysis = await crud_issue_analysis.upsert(
            db=db_session,
            recipient_id=recipient_id,
            staff_id=staff2.id,
            obj_in=analysis_data2
        )

        # created_by_staff_idは最初のスタッフIDのまま
        assert updated_analysis.created_by_staff_id == staff1.id
        assert updated_analysis.what_i_like_to_do == "料理を作ること"
        assert updated_analysis.future_dreams == "シェフになること"
