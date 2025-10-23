"""
アセスメントシート機能のビジネスロジック層

利用者へのアクセス権限検証、全アセスメント情報の取得などを担当します。
"""

from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.staff import Staff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.assessment import (
    FamilyOfServiceRecipients,
    WelfareServicesUsed,
    MedicalMatters,
    HistoryOfHospitalVisits,
    EmploymentRelated,
    IssueAnalysis,
)
from app.schemas.assessment import (
    FamilyMemberResponse,
    FamilyMemberCreate,
    FamilyMemberUpdate,
    ServiceHistoryResponse,
    MedicalInfoResponse,
    MedicalInfoCreate,
    HospitalVisitResponse,
    EmploymentResponse,
    EmploymentCreate,
    IssueAnalysisResponse,
    IssueAnalysisCreate,
    AssessmentResponse,
)
from app.crud.crud_family_member import crud_family_member
from app.crud.crud_medical_info import crud_medical_info
from app.crud.crud_employment import crud_employment
from app.crud.crud_issue_analysis import crud_issue_analysis


async def verify_recipient_access(
    db: AsyncSession,
    recipient_id: UUID,
    current_user: Staff
) -> WelfareRecipient:
    """
    利用者へのアクセス権限を検証

    Args:
        db: データベースセッション
        recipient_id: 利用者のID
        current_user: 現在のユーザー（スタッフ）

    Returns:
        WelfareRecipient: 検証済みの利用者

    Raises:
        HTTPException: 利用者が見つからない場合（404）
        HTTPException: アクセス権限がない場合（403）
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"verify_recipient_access: recipient_id={recipient_id}, user={current_user.email}")

    # 利用者の取得
    stmt = select(WelfareRecipient).where(WelfareRecipient.id == recipient_id)
    result = await db.execute(stmt)
    recipient = result.scalar_one_or_none()

    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="利用者が見つかりません"
        )

    # 利用者が所属する事業所を取得
    stmt = select(OfficeWelfareRecipient).where(
        OfficeWelfareRecipient.welfare_recipient_id == recipient_id
    )
    result = await db.execute(stmt)
    office_recipient_association = result.scalar_one_or_none()

    if not office_recipient_association:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="利用者が事業所に所属していません"
        )

    recipient_office_id = office_recipient_association.office_id

    # 現在のユーザーの所属事業所を取得
    # current_user.officeプロパティ経由でプライマリ事業所を取得
    user_office = current_user.office

    if not user_office:
        logger.error(f"User {current_user.email} has no office")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="事業所に所属していません"
        )

    logger.info(f"Checking access: user_office={user_office.id}, recipient_office={recipient_office_id}")

    # 事業所が一致するかチェック
    if user_office.id != recipient_office_id:
        logger.error(f"Office mismatch: user={user_office.id}, recipient={recipient_office_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="この利用者にアクセスする権限がありません"
        )

    logger.info("Access verification passed")
    return recipient


async def get_all_assessment_data(
    db: AsyncSession,
    recipient_id: UUID,
    current_user: Staff
) -> AssessmentResponse:
    """
    全アセスメント情報を一括取得

    Args:
        db: データベースセッション
        recipient_id: 利用者のID
        current_user: 現在のユーザー（スタッフ）

    Returns:
        AssessmentResponse: 全アセスメント情報

    Raises:
        HTTPException: 利用者が見つからない場合（404）
        HTTPException: アクセス権限がない場合（403）
    """
    # アクセス権限を検証
    await verify_recipient_access(db, recipient_id, current_user)

    # 家族構成を取得
    stmt = select(FamilyOfServiceRecipients).where(
        FamilyOfServiceRecipients.welfare_recipient_id == recipient_id
    )
    result = await db.execute(stmt)
    family_members = result.scalars().all()

    # サービス利用歴を取得（利用開始日の降順）
    stmt = select(WelfareServicesUsed).where(
        WelfareServicesUsed.welfare_recipient_id == recipient_id
    ).order_by(WelfareServicesUsed.starting_day.desc())
    result = await db.execute(stmt)
    service_history = result.scalars().all()

    # 医療基本情報を取得
    stmt = select(MedicalMatters).where(
        MedicalMatters.welfare_recipient_id == recipient_id
    )
    result = await db.execute(stmt)
    medical_info = result.scalar_one_or_none()

    # 通院歴を取得（開始日の降順）
    hospital_visits = []
    if medical_info:
        stmt = select(HistoryOfHospitalVisits).where(
            HistoryOfHospitalVisits.medical_matters_id == medical_info.id
        ).order_by(HistoryOfHospitalVisits.date_started.desc())
        result = await db.execute(stmt)
        hospital_visits = result.scalars().all()

    # 就労関係を取得
    stmt = select(EmploymentRelated).where(
        EmploymentRelated.welfare_recipient_id == recipient_id
    )
    result = await db.execute(stmt)
    employment = result.scalar_one_or_none()

    # 課題分析を取得
    stmt = select(IssueAnalysis).where(
        IssueAnalysis.welfare_recipient_id == recipient_id
    )
    result = await db.execute(stmt)
    issue_analysis = result.scalar_one_or_none()

    # レスポンスを構築
    return AssessmentResponse(
        family_members=[FamilyMemberResponse.model_validate(fm) for fm in family_members],
        service_history=[ServiceHistoryResponse.model_validate(sh) for sh in service_history],
        medical_info=MedicalInfoResponse.model_validate(medical_info) if medical_info else None,
        hospital_visits=[HospitalVisitResponse.model_validate(hv) for hv in hospital_visits],
        employment=EmploymentResponse.model_validate(employment) if employment else None,
        issue_analysis=IssueAnalysisResponse.model_validate(issue_analysis) if issue_analysis else None,
    )


# =============================================================================
# 家族構成関連のサービス層関数
# =============================================================================

async def create_family_member_with_validation(
    db: AsyncSession,
    recipient_id: UUID,
    data: FamilyMemberCreate,
    current_user: Staff
) -> FamilyOfServiceRecipients:
    """
    家族メンバーを作成（権限検証付き）

    Args:
        db: データベースセッション
        recipient_id: 利用者のID
        data: 家族メンバー作成データ
        current_user: 現在のユーザー（スタッフ）

    Returns:
        FamilyOfServiceRecipients: 作成された家族メンバー

    Raises:
        HTTPException: 利用者が見つからない場合（404）
        HTTPException: アクセス権限がない場合（403）
    """
    # アクセス権限を検証
    await verify_recipient_access(db, recipient_id, current_user)

    # 家族メンバーを作成
    family_member = await crud_family_member.create(
        db=db,
        recipient_id=recipient_id,
        obj_in=data
    )

    return family_member


async def update_family_member_with_validation(
    db: AsyncSession,
    family_member_id: int,
    data: FamilyMemberUpdate,
    current_user: Staff
) -> FamilyOfServiceRecipients:
    """
    家族メンバーを更新（権限検証付き）

    Args:
        db: データベースセッション
        family_member_id: 家族メンバーのID
        data: 家族メンバー更新データ
        current_user: 現在のユーザー（スタッフ）

    Returns:
        FamilyOfServiceRecipients: 更新された家族メンバー

    Raises:
        HTTPException: 家族メンバーが見つからない場合（404）
        HTTPException: アクセス権限がない場合（403）
    """
    # 家族メンバーを取得
    stmt = select(FamilyOfServiceRecipients).where(
        FamilyOfServiceRecipients.id == family_member_id
    )
    result = await db.execute(stmt)
    family_member = result.scalar_one_or_none()

    if not family_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="家族メンバーが見つかりません"
        )

    # アクセス権限を検証
    await verify_recipient_access(db, family_member.welfare_recipient_id, current_user)

    # 家族メンバーを更新
    updated_member = await crud_family_member.update(
        db=db,
        family_member_id=family_member_id,
        obj_in=data
    )

    return updated_member


async def delete_family_member_with_validation(
    db: AsyncSession,
    family_member_id: int,
    current_user: Staff
) -> None:
    """
    家族メンバーを削除（権限検証付き）

    Args:
        db: データベースセッション
        family_member_id: 家族メンバーのID
        current_user: 現在のユーザー（スタッフ）

    Raises:
        HTTPException: 家族メンバーが見つからない場合（404）
        HTTPException: アクセス権限がない場合（403）
    """
    # 家族メンバーを取得
    stmt = select(FamilyOfServiceRecipients).where(
        FamilyOfServiceRecipients.id == family_member_id
    )
    result = await db.execute(stmt)
    family_member = result.scalar_one_or_none()

    if not family_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="家族メンバーが見つかりません"
        )

    # アクセス権限を検証
    await verify_recipient_access(db, family_member.welfare_recipient_id, current_user)

    # 家族メンバーを削除
    await crud_family_member.delete(db=db, family_member_id=family_member_id)


# =============================================================================
# 医療基本情報関連のサービス層関数
# =============================================================================

async def upsert_medical_info_with_validation(
    db: AsyncSession,
    recipient_id: UUID,
    data: MedicalInfoCreate,
    current_user: Staff
) -> MedicalMatters:
    """
    医療基本情報を作成または更新（権限検証付き）

    Args:
        db: データベースセッション
        recipient_id: 利用者のID
        data: 医療情報作成データ
        current_user: 現在のユーザー（スタッフ）

    Returns:
        MedicalMatters: 作成または更新された医療情報

    Raises:
        HTTPException: 利用者が見つからない場合（404）
        HTTPException: アクセス権限がない場合（403）
    """
    # アクセス権限を検証
    await verify_recipient_access(db, recipient_id, current_user)

    # 医療情報をupsert
    medical_info = await crud_medical_info.upsert(
        db=db,
        recipient_id=recipient_id,
        obj_in=data
    )

    return medical_info


# =============================================================================
# 就労関係のサービス層関数
# =============================================================================

async def upsert_employment_with_validation(
    db: AsyncSession,
    recipient_id: UUID,
    data: EmploymentCreate,
    current_user: Staff
) -> EmploymentRelated:
    """
    就労関係情報を作成または更新（権限検証付き）

    Args:
        db: データベースセッション
        recipient_id: 利用者のID
        data: 就労情報作成データ
        current_user: 現在のユーザー（スタッフ）

    Returns:
        EmploymentRelated: 作成または更新された就労情報

    Raises:
        HTTPException: 利用者が見つからない場合（404）
        HTTPException: アクセス権限がない場合（403）
    """
    # アクセス権限を検証
    await verify_recipient_access(db, recipient_id, current_user)

    # 就労情報をupsert
    employment = await crud_employment.upsert(
        db=db,
        recipient_id=recipient_id,
        staff_id=current_user.id,
        obj_in=data
    )

    return employment


# =============================================================================
# 課題分析のサービス層関数
# =============================================================================

async def upsert_issue_analysis_with_validation(
    db: AsyncSession,
    recipient_id: UUID,
    data: IssueAnalysisCreate,
    current_user: Staff
) -> IssueAnalysis:
    """
    課題分析を作成または更新（権限検証付き）

    Args:
        db: データベースセッション
        recipient_id: 利用者のID
        data: 課題分析作成データ
        current_user: 現在のユーザー（スタッフ）

    Returns:
        IssueAnalysis: 作成または更新された課題分析

    Raises:
        HTTPException: 利用者が見つからない場合（404）
        HTTPException: アクセス権限がない場合（403）
    """
    # アクセス権限を検証
    await verify_recipient_access(db, recipient_id, current_user)

    # 課題分析をupsert
    issue_analysis = await crud_issue_analysis.upsert(
        db=db,
        recipient_id=recipient_id,
        staff_id=current_user.id,
        obj_in=data
    )

    return issue_analysis
