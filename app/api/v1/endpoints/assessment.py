"""
アセスメントシート機能のAPIエンドポイント

全アセスメント情報の取得、家族構成、医療情報、通院歴、就労関係、課題分析のCRUD操作
"""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.staff import Staff

logger = logging.getLogger(__name__)
from app.schemas.assessment import (
    AssessmentResponse,
    FamilyMemberCreate,
    FamilyMemberUpdate,
    FamilyMemberResponse,
    ServiceHistoryCreate,
    ServiceHistoryUpdate,
    ServiceHistoryResponse,
    MedicalInfoCreate,
    MedicalInfoResponse,
    HospitalVisitCreate,
    HospitalVisitUpdate,
    HospitalVisitResponse,
    EmploymentCreate,
    EmploymentResponse,
    IssueAnalysisCreate,
    IssueAnalysisResponse,
)
from app.services import assessment_service
from app import crud
from app.messages import ja

router = APIRouter()


# ===== 全アセスメント情報 =====

@router.get("/recipients/{recipient_id}/assessment", response_model=AssessmentResponse)
async def get_all_assessment_data(
    recipient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    全アセスメント情報を一括取得
    """
    print("\n" + "="*80)
    print("=== get_all_assessment_data endpoint called ===")
    print(f"recipient_id: {recipient_id}")
    print(f"current_user: {current_user.email if current_user else 'None'}")
    logger.info(f"=== get_all_assessment_data endpoint called ===")
    logger.info(f"recipient_id: {recipient_id}")
    logger.info(f"current_user: {current_user.email if current_user else 'None'}")

    result = await assessment_service.get_all_assessment_data(
        db=db,
        recipient_id=recipient_id,
        current_user=current_user
    )
    print(f"Assessment data retrieved successfully")
    print("="*80 + "\n")
    logger.info(f"Assessment data retrieved successfully")
    return result


# ===== 家族構成 =====

@router.get("/recipients/{recipient_id}/family-members", response_model=List[FamilyMemberResponse])
async def get_family_members(
    recipient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    家族構成一覧を取得
    """
    # アクセス権限を検証
    await assessment_service.verify_recipient_access(db, recipient_id, current_user)

    # 家族構成を取得
    family_members = await crud.family_member.get_family_members(
        db=db,
        recipient_id=recipient_id
    )
    return family_members


@router.post(
    "/recipients/{recipient_id}/family-members",
    response_model=FamilyMemberResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_family_member(
    recipient_id: UUID,
    family_member_in: FamilyMemberCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    家族メンバーを追加
    """
    # アクセス権限を検証
    await assessment_service.verify_recipient_access(db, recipient_id, current_user)

    # 家族メンバーを作成
    family_member = await crud.family_member.create(
        db=db,
        recipient_id=recipient_id,
        obj_in=family_member_in
    )
    return family_member


@router.patch("/family-members/{family_member_id}", response_model=FamilyMemberResponse)
async def update_family_member(
    family_member_id: int,
    family_member_in: FamilyMemberUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    家族メンバー情報を更新
    """
    # 家族メンバーを更新
    family_member = await crud.family_member.update(
        db=db,
        family_member_id=family_member_id,
        obj_in=family_member_in
    )

    if not family_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.ASSESSMENT_FAMILY_MEMBER_NOT_FOUND
        )

    return family_member


@router.delete("/family-members/{family_member_id}")
async def delete_family_member(
    family_member_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    家族メンバーを削除
    """
    success = await crud.family_member.delete(
        db=db,
        family_member_id=family_member_id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.ASSESSMENT_FAMILY_MEMBER_NOT_FOUND
        )

    return {"message": "家族メンバーを削除しました"}


# ===== 福祉サービス利用歴 =====

@router.get("/recipients/{recipient_id}/service-history", response_model=List[ServiceHistoryResponse])
async def get_service_history(
    recipient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    福祉サービス利用歴一覧を取得
    """
    # アクセス権限を検証
    await assessment_service.verify_recipient_access(db, recipient_id, current_user)

    # サービス利用歴を取得
    service_history = await crud.service_history.get_service_history(
        db=db,
        recipient_id=recipient_id
    )
    return service_history


@router.post(
    "/recipients/{recipient_id}/service-history",
    response_model=ServiceHistoryResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_service_history(
    recipient_id: UUID,
    service_history_in: ServiceHistoryCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    福祉サービス利用歴を追加
    """
    # アクセス権限を検証
    await assessment_service.verify_recipient_access(db, recipient_id, current_user)

    # サービス利用歴を作成
    service_history = await crud.service_history.create(
        db=db,
        recipient_id=recipient_id,
        obj_in=service_history_in
    )
    return service_history


@router.patch("/service-history/{history_id}", response_model=ServiceHistoryResponse)
async def update_service_history(
    history_id: int,
    service_history_in: ServiceHistoryUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    福祉サービス利用歴を更新
    """
    # サービス利用歴を更新
    service_history = await crud.service_history.update(
        db=db,
        history_id=history_id,
        obj_in=service_history_in
    )

    if not service_history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.ASSESSMENT_SERVICE_HISTORY_NOT_FOUND
        )

    return service_history


@router.delete("/service-history/{history_id}")
async def delete_service_history(
    history_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    福祉サービス利用歴を削除
    """
    success = await crud.service_history.delete(
        db=db,
        history_id=history_id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.ASSESSMENT_SERVICE_HISTORY_NOT_FOUND
        )

    return {"message": "サービス利用歴を削除しました"}


# ===== 医療基本情報 =====

@router.get("/recipients/{recipient_id}/medical-info", response_model=MedicalInfoResponse | None)
async def get_medical_info(
    recipient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    医療基本情報を取得
    """
    # アクセス権限を検証
    await assessment_service.verify_recipient_access(db, recipient_id, current_user)

    # 医療情報を取得
    medical_info = await crud.medical_info.get_medical_info(
        db=db,
        recipient_id=recipient_id
    )
    return medical_info


@router.put("/recipients/{recipient_id}/medical-info", response_model=MedicalInfoResponse)
async def upsert_medical_info(
    recipient_id: UUID,
    medical_info_in: MedicalInfoCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    医療基本情報を作成または更新
    """
    # アクセス権限を検証
    await assessment_service.verify_recipient_access(db, recipient_id, current_user)

    # upsertメソッドを使用して作成または更新
    medical_info = await crud.medical_info.upsert(
        db=db,
        recipient_id=recipient_id,
        obj_in=medical_info_in
    )
    return medical_info


# ===== 通院歴 =====

@router.get("/recipients/{recipient_id}/hospital-visits", response_model=List[HospitalVisitResponse])
async def get_hospital_visits(
    recipient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    通院歴一覧を取得
    """
    # アクセス権限を検証
    await assessment_service.verify_recipient_access(db, recipient_id, current_user)

    # 通院歴を取得
    hospital_visits = await crud.hospital_visit.get_hospital_visits(
        db=db,
        recipient_id=recipient_id
    )
    return hospital_visits


@router.post(
    "/recipients/{recipient_id}/hospital-visits",
    response_model=HospitalVisitResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_hospital_visit(
    recipient_id: UUID,
    hospital_visit_in: HospitalVisitCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    通院歴を追加
    """
    # アクセス権限を検証
    await assessment_service.verify_recipient_access(db, recipient_id, current_user)

    # 通院歴を作成
    hospital_visit = await crud.hospital_visit.create(
        db=db,
        recipient_id=recipient_id,
        obj_in=hospital_visit_in
    )
    return hospital_visit


@router.patch("/hospital-visits/{visit_id}", response_model=HospitalVisitResponse)
async def update_hospital_visit(
    visit_id: int,
    hospital_visit_in: HospitalVisitUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    通院歴を更新
    """
    # 通院歴を更新
    hospital_visit = await crud.hospital_visit.update(
        db=db,
        visit_id=visit_id,
        obj_in=hospital_visit_in
    )

    if not hospital_visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.ASSESSMENT_HOSPITAL_VISIT_NOT_FOUND
        )

    return hospital_visit


@router.delete("/hospital-visits/{visit_id}")
async def delete_hospital_visit(
    visit_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    通院歴を削除
    """
    success = await crud.hospital_visit.delete(
        db=db,
        visit_id=visit_id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.ASSESSMENT_HOSPITAL_VISIT_NOT_FOUND
        )

    return {"message": "通院歴を削除しました"}


# ===== 就労関係 =====

@router.get("/recipients/{recipient_id}/employment", response_model=EmploymentResponse | None)
async def get_employment(
    recipient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    就労関係情報を取得
    """
    # アクセス権限を検証
    await assessment_service.verify_recipient_access(db, recipient_id, current_user)

    # 就労関係を取得
    employment = await crud.employment.get_employment(
        db=db,
        recipient_id=recipient_id
    )
    return employment


@router.put("/recipients/{recipient_id}/employment", response_model=EmploymentResponse)
async def upsert_employment(
    recipient_id: UUID,
    employment_in: EmploymentCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    就労関係情報を作成または更新
    """
    # サービス層を呼び出し（監査ログ含む）
    employment = await assessment_service.upsert_employment_with_validation(
        db=db,
        recipient_id=recipient_id,
        data=employment_in,
        current_user=current_user
    )
    return employment


# ===== 課題分析 =====

@router.get("/recipients/{recipient_id}/issue-analysis", response_model=IssueAnalysisResponse | None)
async def get_issue_analysis(
    recipient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    課題分析を取得
    """
    # アクセス権限を検証
    await assessment_service.verify_recipient_access(db, recipient_id, current_user)

    # 課題分析を取得
    issue_analysis = await crud.issue_analysis.get_issue_analysis(
        db=db,
        recipient_id=recipient_id
    )
    return issue_analysis


@router.put("/recipients/{recipient_id}/issue-analysis", response_model=IssueAnalysisResponse)
async def upsert_issue_analysis(
    recipient_id: UUID,
    issue_analysis_in: IssueAnalysisCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    課題分析を作成または更新
    """
    # アクセス権限を検証
    await assessment_service.verify_recipient_access(db, recipient_id, current_user)

    # upsert（作成または更新）
    issue_analysis = await crud.issue_analysis.upsert(
        db=db,
        recipient_id=recipient_id,
        staff_id=current_user.id,
        obj_in=issue_analysis_in
    )
    return issue_analysis
