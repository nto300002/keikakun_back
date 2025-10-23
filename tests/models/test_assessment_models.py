import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import datetime
import uuid

from app.models.assessment import (
    FamilyOfServiceRecipients,
    WelfareServicesUsed,
    MedicalMatters,
    HistoryOfHospitalVisits,
    EmploymentRelated,
    IssueAnalysis,
)
from app.models.enums import (
    Household,
    MedicalCareInsurance,
    AidingType,
    WorkConditions,
    WorkOutsideFacility,
)
from app.models.welfare_recipient import WelfareRecipient
from app.models.enums import GenderType
from app.models.staff import Staff
from app.models.office import Office
from app.models.enums import StaffRole, OfficeType

pytestmark = pytest.mark.asyncio


async def test_create_family_member(db_session: AsyncSession):
    """家族構成の基本的な作成テスト"""
    # まず受給者を作成
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

    # 家族構成を作成
    family_member = FamilyOfServiceRecipients(
        welfare_recipient_id=recipient.id,
        name="花子",
        relationship="母",
        household=Household.same,
        ones_health="良好",
        remarks="特になし",
    )
    db_session.add(family_member)
    await db_session.commit()
    await db_session.refresh(family_member)

    assert family_member.id is not None
    assert family_member.name == "花子"
    assert family_member.relationship == "母"
    assert family_member.household == Household.same
    assert family_member.ones_health == "良好"


async def test_create_welfare_services_used(db_session: AsyncSession):
    """福祉サービス利用歴の基本的な作成テスト"""
    # 受給者を作成
    recipient = WelfareRecipient(
        first_name="花子",
        last_name="鈴木",
        first_name_furigana="はなこ",
        last_name_furigana="すずき",
        birth_day=datetime.date(1988, 4, 1),
        gender=GenderType.female,
    )
    db_session.add(recipient)
    await db_session.commit()
    await db_session.refresh(recipient)

    # サービス利用歴を作成
    service = WelfareServicesUsed(
        welfare_recipient_id=recipient.id,
        office_name="ABC就労支援センター",
        starting_day=datetime.date(2020, 4, 1),
        amount_used="月80時間",
        service_name="就労継続支援B型",
    )
    db_session.add(service)
    await db_session.commit()
    await db_session.refresh(service)

    assert service.id is not None
    assert service.office_name == "ABC就労支援センター"
    assert service.starting_day == datetime.date(2020, 4, 1)
    assert service.amount_used == "月80時間"
    assert service.service_name == "就労継続支援B型"


async def test_create_medical_matters(db_session: AsyncSession):
    """医療基本情報の作成テスト"""
    # 受給者を作成
    recipient = WelfareRecipient(
        first_name="次郎",
        last_name="田中",
        first_name_furigana="じろう",
        last_name_furigana="たなか",
        birth_day=datetime.date(1985, 7, 15),
        gender=GenderType.male,
    )
    db_session.add(recipient)
    await db_session.commit()
    await db_session.refresh(recipient)

    # 医療基本情報を作成
    medical = MedicalMatters(
        welfare_recipient_id=recipient.id,
        medical_care_insurance=MedicalCareInsurance.national_health_insurance,
        aiding=AidingType.subsidized,
        history_of_hospitalization_in_the_past_2_years=True,
    )
    db_session.add(medical)
    await db_session.commit()
    await db_session.refresh(medical)

    assert medical.id is not None
    assert medical.medical_care_insurance == MedicalCareInsurance.national_health_insurance
    assert medical.aiding == AidingType.subsidized
    assert medical.history_of_hospitalization_in_the_past_2_years is True


async def test_create_hospital_visit_with_medical_matters(db_session: AsyncSession):
    """通院歴と医療基本情報の関連テスト"""
    # 受給者を作成
    recipient = WelfareRecipient(
        first_name="美咲",
        last_name="佐藤",
        first_name_furigana="みさき",
        last_name_furigana="さとう",
        birth_day=datetime.date(1992, 3, 20),
        gender=GenderType.female,
    )
    db_session.add(recipient)
    await db_session.commit()
    await db_session.refresh(recipient)

    # 医療基本情報を作成
    medical = MedicalMatters(
        welfare_recipient_id=recipient.id,
        medical_care_insurance=MedicalCareInsurance.social_insurance,
        aiding=AidingType.none,
        history_of_hospitalization_in_the_past_2_years=False,
    )
    db_session.add(medical)
    await db_session.commit()
    await db_session.refresh(medical)

    # 通院歴を作成
    hospital_visit = HistoryOfHospitalVisits(
        medical_matters_id=medical.id,
        disease="うつ病",
        frequency_of_hospital_visits="月1回",
        symptoms="気分の落ち込み",
        medical_institution="さくら病院",
        doctor="山田医師",
        tel="03-1234-5678",
        taking_medicine=True,
        date_started=datetime.date(2021, 1, 10),
        special_remarks="定期的な診察が必要",
    )
    db_session.add(hospital_visit)
    await db_session.commit()
    await db_session.refresh(hospital_visit)

    assert hospital_visit.id is not None
    assert hospital_visit.disease == "うつ病"
    assert hospital_visit.medical_institution == "さくら病院"
    assert hospital_visit.taking_medicine is True

    # リレーションシップの確認
    stmt = select(MedicalMatters).where(MedicalMatters.id == medical.id).options(
        selectinload(MedicalMatters.hospital_visits)
    )
    result = await db_session.execute(stmt)
    retrieved_medical = result.scalar_one()

    assert len(retrieved_medical.hospital_visits) == 1
    assert retrieved_medical.hospital_visits[0].disease == "うつ病"


async def test_create_employment_related(db_session: AsyncSession):
    """就労関係情報の作成テスト"""
    # 受給者を作成
    recipient = WelfareRecipient(
        first_name="健太",
        last_name="伊藤",
        first_name_furigana="けんた",
        last_name_furigana="いとう",
        birth_day=datetime.date(1993, 11, 5),
        gender=GenderType.male,
    )
    db_session.add(recipient)
    await db_session.commit()
    await db_session.refresh(recipient)

    # スタッフを作成（就労関係情報の作成者として必要）
    staff = Staff(
        name="管理一郎",
        email="manager@example.com",
        hashed_password="dummy_hash",
        role=StaffRole.manager,
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)

    office = Office(
        name="テスト事業所",
        type=OfficeType.type_B_office,
        created_by=staff.id,
        last_modified_by=staff.id,
    )
    db_session.add(office)
    await db_session.commit()
    await db_session.refresh(office)


    # 就労関係情報を作成
    employment = EmploymentRelated(
        welfare_recipient_id=recipient.id,
        created_by_staff_id=staff.id,
        work_conditions=WorkConditions.continuous_support_b,
        regular_or_part_time_job=False,
        employment_support=True,
        work_experience_in_the_past_year=False,
        suspension_of_work=False,
        qualifications="普通自動車免許",
        main_places_of_employment="過去に製造業での勤務経験あり",
        general_employment_request=True,
        desired_job="事務職",
        special_remarks="パソコン操作が得意",
        work_outside_the_facility=WorkOutsideFacility.hope,
        special_note_about_working_outside_the_facility="通勤可能範囲であれば積極的に参加したい",
    )
    db_session.add(employment)
    await db_session.commit()
    await db_session.refresh(employment)

    assert employment.id is not None
    assert employment.work_conditions == WorkConditions.continuous_support_b
    assert employment.general_employment_request is True
    assert employment.work_outside_the_facility == WorkOutsideFacility.hope
    assert employment.desired_job == "事務職"


async def test_create_issue_analysis(db_session: AsyncSession):
    """課題分析の作成テスト"""
    # 受給者を作成
    recipient = WelfareRecipient(
        first_name="舞",
        last_name="小林",
        first_name_furigana="まい",
        last_name_furigana="こばやし",
        birth_day=datetime.date(1995, 6, 12),
        gender=GenderType.female,
    )
    db_session.add(recipient)
    await db_session.commit()
    await db_session.refresh(recipient)

    # スタッフを作成
    staff = Staff(
        name="支援花子",
        email="shien@example.com",
        hashed_password="dummy_hash",
        role=StaffRole.employee,
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)

    office = Office(
        name="分析テスト事業所",
        type=OfficeType.type_A_office,
        created_by=staff.id,
        last_modified_by=staff.id,
    )
    db_session.add(office)
    await db_session.commit()
    await db_session.refresh(office)


    # 課題分析を作成
    analysis = IssueAnalysis(
        welfare_recipient_id=recipient.id,
        created_by_staff_id=staff.id,
        what_i_like_to_do="絵を描くこと、音楽を聴くこと",
        im_not_good_at="人前で話すこと、計算",
        the_life_i_want="自立した生活を送りたい",
        the_support_i_want="就労に向けたスキルアップのサポート",
        points_to_keep_in_mind_when_providing_support="ゆっくりとした説明が必要",
        future_dreams="デザイナーとして働くこと",
        other="特になし",
    )
    db_session.add(analysis)
    await db_session.commit()
    await db_session.refresh(analysis)

    assert analysis.id is not None
    assert analysis.what_i_like_to_do == "絵を描くこと、音楽を聴くこと"
    assert analysis.the_life_i_want == "自立した生活を送りたい"
    assert analysis.future_dreams == "デザイナーとして働くこと"


async def test_full_assessment_with_relationships(db_session: AsyncSession):
    """すべてのアセスメント情報を含む統合テスト"""
    # 受給者を作成
    recipient = WelfareRecipient(
        first_name="統合",
        last_name="テスト",
        first_name_furigana="とうごう",
        last_name_furigana="てすと",
        birth_day=datetime.date(1990, 5, 5),
        gender=GenderType.other,
    )
    db_session.add(recipient)
    await db_session.commit()
    await db_session.refresh(recipient)

    # スタッフと事業所を作成
    staff = Staff(
        name="統合太郎",
        email="togo@example.com",
        hashed_password="dummy_hash",
        role=StaffRole.owner,
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)

    office = Office(
        name="統合テスト事業所",
        type=OfficeType.transition_to_employment,
        created_by=staff.id,
        last_modified_by=staff.id,
    )
    db_session.add(office)
    await db_session.commit()
    await db_session.refresh(office)


    # 家族構成を追加
    family1 = FamilyOfServiceRecipients(
        welfare_recipient_id=recipient.id,
        name="父親",
        relationship="父",
        household=Household.same,
        ones_health="良好",
    )
    family2 = FamilyOfServiceRecipients(
        welfare_recipient_id=recipient.id,
        name="母親",
        relationship="母",
        household=Household.same,
        ones_health="持病あり",
        remarks="糖尿病治療中",
    )
    db_session.add_all([family1, family2])

    # サービス利用歴を追加
    service1 = WelfareServicesUsed(
        welfare_recipient_id=recipient.id,
        office_name="以前の事業所A",
        starting_day=datetime.date(2018, 4, 1),
        amount_used="月60時間",
        service_name="就労移行支援",
    )
    db_session.add(service1)

    # 医療情報と通院歴を追加
    medical = MedicalMatters(
        welfare_recipient_id=recipient.id,
        medical_care_insurance=MedicalCareInsurance.social_insurance,
        aiding=AidingType.subsidized,
        history_of_hospitalization_in_the_past_2_years=True,
    )
    db_session.add(medical)
    await db_session.commit()
    await db_session.refresh(medical)

    hospital_visit = HistoryOfHospitalVisits(
        medical_matters_id=medical.id,
        disease="統合失調症",
        frequency_of_hospital_visits="月2回",
        symptoms="幻聴、妄想",
        medical_institution="総合病院",
        doctor="鈴木医師",
        tel="03-9999-0000",
        taking_medicine=True,
        date_started=datetime.date(2015, 3, 1),
    )
    db_session.add(hospital_visit)

    # 就労関係情報を追加
    employment = EmploymentRelated(
        welfare_recipient_id=recipient.id,
        created_by_staff_id=staff.id,
        work_conditions=WorkConditions.transition_support,
        regular_or_part_time_job=False,
        employment_support=True,
        work_experience_in_the_past_year=True,
        suspension_of_work=False,
        general_employment_request=True,
        work_outside_the_facility=WorkOutsideFacility.hope,
    )
    db_session.add(employment)

    # 課題分析を追加
    analysis = IssueAnalysis(
        welfare_recipient_id=recipient.id,
        created_by_staff_id=staff.id,
        what_i_like_to_do="読書、散歩",
        im_not_good_at="人混み",
        the_life_i_want="安定した仕事を持ち、一人暮らしをしたい",
        the_support_i_want="就労と生活の両面でのサポート",
        points_to_keep_in_mind_when_providing_support="ストレス管理が重要",
        future_dreams="図書館で働くこと",
    )
    db_session.add(analysis)

    await db_session.commit()

    # すべてのデータが正しく作成されたことを確認
    stmt = select(WelfareRecipient).where(WelfareRecipient.id == recipient.id).options(
        selectinload(WelfareRecipient.family_members),
        selectinload(WelfareRecipient.service_history),
        selectinload(WelfareRecipient.medical_matters).selectinload(MedicalMatters.hospital_visits),
        selectinload(WelfareRecipient.employment_related),
        selectinload(WelfareRecipient.issue_analysis),
    )
    result = await db_session.execute(stmt)
    retrieved_recipient = result.scalar_one()

    # 検証
    assert len(retrieved_recipient.family_members) == 2
    assert len(retrieved_recipient.service_history) == 1
    assert retrieved_recipient.medical_matters is not None
    assert len(retrieved_recipient.medical_matters.hospital_visits) == 1
    assert retrieved_recipient.employment_related is not None
    assert retrieved_recipient.issue_analysis is not None
