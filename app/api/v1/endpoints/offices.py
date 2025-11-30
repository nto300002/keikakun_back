from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import crud, models, schemas
from app.api import deps
from app.messages import ja

router = APIRouter()


@router.get("/", response_model=list[schemas.OfficeResponse])
async def read_offices(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    すべての事業所の一覧を取得する（employee/managerが選択するため）
    """
    offices = await crud.office.get_multi(db)
    return offices


@router.get("/me", response_model=schemas.OfficeResponse)
async def read_my_office(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    現在ログインしているユーザーが所属する事業所の情報を取得する
    """
    # ユーザーの所属情報を eager load する
    stmt = (
        select(models.Staff)
        .options(selectinload(models.Staff.office_associations)
        .selectinload(models.OfficeStaff.office))
        .where(models.Staff.id == current_user.id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_NOT_FOUND_FOR_USER,
        )

    # ユーザーは複数の事業所に所属できる設計になっているが、
    # 現状は最初の事業所を返す（多くの場合は一つのはず）
    office = user.office_associations[0].office
    if not office:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_INFO_NOT_FOUND,
        )

    return office


@router.post("/setup", response_model=schemas.OfficeResponse, status_code=status.HTTP_201_CREATED)
async def setup_office(
    *, 
    db: AsyncSession = Depends(deps.get_db),
    office_in: schemas.OfficeCreate,
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    事業所を新規作成し、作成したユーザーを事業所に所属させる
    """
    if current_user.role != models.StaffRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.PERM_OPERATION_FORBIDDEN,
        )

    # DBから最新のユーザー情報を取得し、関連をロード
    stmt = select(models.Staff).options(selectinload(models.Staff.office_associations)).where(models.Staff.id == current_user.id)
    result = await db.execute(stmt)
    user_in_db = result.scalar_one_or_none()
    if not user_in_db:
        raise HTTPException(status_code=404, detail=ja.OFFICE_USER_NOT_FOUND)

    if user_in_db.office_associations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.OFFICE_ALREADY_ASSOCIATED,
        )

    # 同じ名前の事業所が既に存在するかチェック
    existing_office = await crud.office.get_by_name(db, name=office_in.name)
    if existing_office:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ja.OFFICE_NAME_ALREADY_EXISTS,
        )

    try:
        office = await crud.office.create_with_owner(db=db, obj_in=office_in, user=user_in_db)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ja.OFFICE_NAME_ALREADY_EXISTS,
        )

    return office


@router.get("/me/staffs", response_model=list[schemas.staff.StaffRead])
async def get_office_staffs(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.require_manager_or_owner),
) -> Any:
    """
    現在ログインしているユーザーの所属事務所の全スタッフを取得

    権限: Manager または Owner のみアクセス可能
    Employee がアクセスした場合は 403 Forbidden を返す
    """
    # ユーザーの所属情報を eager load する
    stmt = (
        select(models.Staff)
        .options(selectinload(models.Staff.office_associations)
        .selectinload(models.OfficeStaff.office))
        .where(models.Staff.id == current_user.id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_NOT_FOUND_FOR_USER,
        )

    # ユーザーの所属事務所を取得（最初の事務所）
    office = user.office_associations[0].office
    if not office:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_INFO_NOT_FOUND,
        )

    # 事務所に所属する全スタッフを取得
    stmt_staffs = (
        select(models.Staff)
        .join(models.OfficeStaff, models.Staff.id == models.OfficeStaff.staff_id)
        .where(models.OfficeStaff.office_id == office.id)
        .options(selectinload(models.Staff.office_associations))
    )
    result_staffs = await db.execute(stmt_staffs)
    staffs = result_staffs.scalars().all()

    return staffs


@router.get("/me/staffs/all", response_model=list[schemas.staff.StaffRead])
async def get_all_office_staffs(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    現在ログインしているユーザーの所属事務所の全スタッフを取得

    権限: 全ユーザー（Employee/Manager/Owner）がアクセス可能
    メッセージ送信などで使用
    """
    # ユーザーの所属情報を eager load する
    stmt = (
        select(models.Staff)
        .options(selectinload(models.Staff.office_associations)
        .selectinload(models.OfficeStaff.office))
        .where(models.Staff.id == current_user.id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_NOT_FOUND_FOR_USER,
        )

    # ユーザーの所属事務所を取得（最初の事務所）
    office = user.office_associations[0].office
    if not office:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_INFO_NOT_FOUND,
        )

    # 事務所に所属する全スタッフを取得
    stmt_staffs = (
        select(models.Staff)
        .join(models.OfficeStaff, models.Staff.id == models.OfficeStaff.staff_id)
        .where(models.OfficeStaff.office_id == office.id)
        .options(selectinload(models.Staff.office_associations))
    )
    result_staffs = await db.execute(stmt_staffs)
    staffs = result_staffs.scalars().all()

    return staffs

@router.put("/me", response_model=schemas.OfficeResponse)
async def update_office_info(
    *,
    request: Request,
    db: AsyncSession = Depends(deps.get_db),
    office_in: schemas.OfficeInfoUpdate,
    current_user: models.Staff = Depends(deps.require_owner),
    _: None = Depends(deps.validate_csrf),
) -> Any:
    """
    事務所情報を更新（オーナーのみ）

    権限: Owner のみアクセス可能
    更新と監査ログ作成を同一トランザクションで実行
    CSRF保護: Cookie認証の場合はCSRFトークンが必要
    """
    # ユーザーの所属情報を eager load する
    stmt = (
        select(models.Staff)
        .options(selectinload(models.Staff.office_associations)
        .selectinload(models.OfficeStaff.office))
        .where(models.Staff.id == current_user.id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_NOT_FOUND_FOR_USER,
        )

    # ユーザーの所属事務所を取得
    office = user.office_associations[0].office
    if not office:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_INFO_NOT_FOUND,
        )

    # 変更前の値を保存（監査ログ用）
    update_data = office_in.model_dump(exclude_unset=True)
    if not update_data:
        # 更新データがない場合は現在の情報を返す
        return office

    old_values = {}
    for key in update_data.keys():
        if hasattr(office, key):
            old_values[key] = getattr(office, key)

    try:
        # 事務所情報を更新（flush のみ）
        updated_office = await crud.office.update_office_info(
            db=db,
            office_id=office.id,
            update_data=update_data
        )

        # 監査ログを作成（flush のみ）
        await crud.audit_log.create_log(
            db=db,
            actor_id=current_user.id,
            action="office.updated",
            target_type="office",
            target_id=office.id,
            office_id=office.id,
            actor_role=current_user.role.value,
            details={
                "old_values": old_values,
                "new_values": update_data
            }
        )

        # システム通知を作成（flush のみ）
        # 事務所内の全スタッフに通知を送信
        active_staffs = await crud.staff.get_by_office_id(
            db=db,
            office_id=office.id,
            exclude_deleted=True
        )

        if active_staffs:
            # フィールド名を日本語に変換するマッピング
            field_name_mapping = {
                "name": "名前",
                "type": "事務所種別",
                "address": "住所",
                "phone_number": "電話番号",
                "email": "メールアドレス"
            }

            # 変更されたフィールドを日本語名に変換
            changed_fields_ja = [
                field_name_mapping.get(field, field)
                for field in update_data.keys()
            ]
            changed_fields_str = "、".join(changed_fields_ja)

            # システム通知を作成
            notification_title = "事務所情報が更新されました"
            notification_content = f"変更内容: {changed_fields_str}"

            await crud.message.create_announcement(
                db=db,
                obj_in={
                    "sender_staff_id": None,  # システム通知はsender_idがNone
                    "office_id": office.id,
                    "recipient_ids": [staff.id for staff in active_staffs],
                    "title": notification_title,
                    "content": notification_content
                }
            )

        # すべての操作が成功したら commit
        await db.commit()
        await db.refresh(updated_office)

        return updated_office

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update office info: {str(e)}"
        )


@router.get("/me/audit-logs", response_model=dict)
async def get_office_audit_logs(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.require_owner),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    事務所の監査ログを取得（オーナーのみ）

    権限: Owner のみアクセス可能
    """
    # ユーザーの所属情報を eager load する
    stmt = (
        select(models.Staff)
        .options(selectinload(models.Staff.office_associations)
        .selectinload(models.OfficeStaff.office))
        .where(models.Staff.id == current_user.id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_NOT_FOUND_FOR_USER,
        )

    # ユーザーの所属事務所を取得
    office = user.office_associations[0].office
    if not office:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_INFO_NOT_FOUND,
        )

    # 統合監査ログから事務所関連のログを取得
    logs, total = await crud.audit_log.get_logs(
        db=db,
        office_id=office.id,
        target_type="office",
        skip=skip,
        limit=limit
    )

    # レスポンス形式に変換
    log_responses = []
    for log in logs:
        log_responses.append({
            "id": log.id,
            "office_id": log.office_id,
            "staff_id": log.staff_id,
            "action_type": log.action,
            "details": log.details,
            "created_at": log.timestamp
        })

    return {
        "logs": log_responses,
        "total": total
    }
