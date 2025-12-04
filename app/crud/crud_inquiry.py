"""
問い合わせCRUD操作

問い合わせの作成、取得、更新、削除を提供
Message と InquiryDetail の両方を管理
"""
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update, delete, func, and_, or_

from app.crud.base import CRUDBase
from app.models.inquiry import InquiryDetail
from app.models.message import Message, MessageRecipient
from app.models.enums import (
    InquiryStatus, InquiryPriority, MessageType, MessagePriority
)


class CRUDInquiry(CRUDBase[InquiryDetail, dict, dict]):
    """問い合わせCRUD操作クラス"""

    async def create_inquiry(
        self,
        db: AsyncSession,
        *,
        sender_staff_id: Optional[UUID],
        office_id: UUID,
        title: str,
        content: str,
        priority: InquiryPriority,
        admin_recipient_ids: List[UUID],
        sender_name: Optional[str] = None,
        sender_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        is_test_data: bool = False
    ) -> InquiryDetail:
        """
        問い合わせを作成

        Args:
            db: データベースセッション
            sender_staff_id: 送信者スタッフID（ログイン済みの場合）
            office_id: 事務所ID
            title: 件名
            content: 内容
            priority: 優先度
            admin_recipient_ids: 受信者（app_admin）のIDリスト
            sender_name: 送信者名（未ログインの場合）
            sender_email: 送信者メールアドレス（未ログインの場合）
            ip_address: 送信元IPアドレス
            user_agent: ユーザーエージェント
            is_test_data: テストデータフラグ

        Returns:
            作成されたInquiryDetail（Message情報を含む）

        Note:
            - 1トランザクションで Message, InquiryDetail, MessageRecipient を作成
            - commitはエンドポイントで行う
        """
        # Message 優先度のマッピング
        message_priority_map = {
            InquiryPriority.low: MessagePriority.low,
            InquiryPriority.normal: MessagePriority.normal,
            InquiryPriority.high: MessagePriority.high,
        }

        # 1. Message を作成
        message = Message(
            sender_staff_id=sender_staff_id,
            office_id=office_id,
            message_type=MessageType.inquiry,
            priority=message_priority_map.get(priority, MessagePriority.normal),
            title=title,
            content=content,
            is_test_data=is_test_data
        )
        db.add(message)
        await db.flush()  # message.id を取得

        # 2. InquiryDetail を作成
        inquiry_detail = InquiryDetail(
            message_id=message.id,
            sender_name=sender_name,
            sender_email=sender_email,
            ip_address=ip_address,
            user_agent=user_agent,
            status=InquiryStatus.new,
            priority=priority,
            assigned_staff_id=None,
            admin_notes=None,
            delivery_log=None,
            is_test_data=is_test_data
        )
        db.add(inquiry_detail)
        await db.flush()

        # 3. MessageRecipient を作成（app_admin 宛）
        recipients = [
            MessageRecipient(
                message_id=message.id,
                recipient_staff_id=recipient_id,
                is_read=False,
                is_archived=False,
                is_test_data=is_test_data
            )
            for recipient_id in admin_recipient_ids
        ]
        db.add_all(recipients)
        await db.flush()

        # 4. リレーションシップをロード
        await db.refresh(inquiry_detail, ["message"])
        await db.refresh(message, ["recipients"])

        return inquiry_detail

    async def get_inquiries(
        self,
        db: AsyncSession,
        *,
        status: Optional[InquiryStatus] = None,
        assigned_staff_id: Optional[UUID] = None,
        priority: Optional[InquiryPriority] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
        include_test_data: bool = False
    ) -> Tuple[List[InquiryDetail], int]:
        """
        問い合わせ一覧を取得

        Args:
            db: データベースセッション
            status: ステータスフィルタ
            assigned_staff_id: 担当者フィルタ
            priority: 優先度フィルタ
            search: 検索キーワード（件名・本文）
            skip: オフセット
            limit: 取得件数
            sort: ソートカラム（created_at, updated_at, priority）
            order: ソート順（asc, desc）
            include_test_data: テストデータを含めるか

        Returns:
            (問い合わせリスト, 総件数)
        """
        # フィルタ条件を構築
        conditions = []

        # テストデータフィルタ
        if not include_test_data:
            conditions.append(InquiryDetail.is_test_data == False)  # noqa: E712

        if status is not None:
            conditions.append(InquiryDetail.status == status)

        if assigned_staff_id is not None:
            conditions.append(InquiryDetail.assigned_staff_id == assigned_staff_id)

        if priority is not None:
            conditions.append(InquiryDetail.priority == priority)

        # 検索条件（SQLインジェクション対策）
        if search:
            # ワイルドカード文字をエスケープ
            escaped_search = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            search_condition = or_(
                Message.title.ilike(f"%{escaped_search}%", escape='\\'),
                Message.content.ilike(f"%{escaped_search}%", escape='\\')
            )
            conditions.append(search_condition)

        where_clause = and_(*conditions) if conditions else True

        # 総件数を取得（効率的なカウント）
        count_query = select(func.count()).select_from(InquiryDetail)
        if search:
            count_query = count_query.join(Message, InquiryDetail.message_id == Message.id)
        count_query = count_query.where(where_clause)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # データ取得クエリ
        query = (
            select(InquiryDetail)
            .options(
                selectinload(InquiryDetail.message),
                selectinload(InquiryDetail.assigned_staff)
            )
        )

        if search:
            query = query.join(Message, InquiryDetail.message_id == Message.id)

        query = query.where(where_clause)

        # ソート（決定的な順序のため id を副次ソートキーに追加）
        sort_column = getattr(InquiryDetail, sort, InquiryDetail.created_at)
        if order == "asc":
            query = query.order_by(sort_column.asc(), InquiryDetail.id.asc())
        else:
            query = query.order_by(sort_column.desc(), InquiryDetail.id.desc())

        # ページネーション
        query = query.offset(skip).limit(limit)

        # 実行
        result = await db.execute(query)
        inquiries = list(result.scalars().unique().all())

        return inquiries, total

    async def get_inquiry_by_id(
        self,
        db: AsyncSession,
        *,
        inquiry_id: UUID
    ) -> Optional[InquiryDetail]:
        """
        問い合わせ詳細を取得

        Args:
            db: データベースセッション
            inquiry_id: 問い合わせID

        Returns:
            InquiryDetail または None
        """
        query = select(InquiryDetail).options(
            selectinload(InquiryDetail.message).selectinload(Message.recipients),
            selectinload(InquiryDetail.assigned_staff)
        ).where(InquiryDetail.id == inquiry_id)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def update_inquiry(
        self,
        db: AsyncSession,
        *,
        inquiry_id: UUID,
        status: Optional[InquiryStatus] = None,
        assigned_staff_id: Optional[UUID] = None,
        priority: Optional[InquiryPriority] = None,
        admin_notes: Optional[str] = None
    ) -> InquiryDetail:
        """
        問い合わせを更新

        Args:
            db: データベースセッション
            inquiry_id: 問い合わせID
            status: 新しいステータス
            assigned_staff_id: 新しい担当者ID
            priority: 新しい優先度
            admin_notes: 新しい管理者メモ

        Returns:
            更新された InquiryDetail

        Raises:
            ValueError: 問い合わせが見つからない場合

        Note:
            - 指定されたフィールドのみ更新
            - updated_at は自動更新される
        """
        # 既存のInquiryDetailを取得して存在確認
        inquiry = await self.get_inquiry_by_id(db=db, inquiry_id=inquiry_id)
        if not inquiry:
            raise ValueError("問い合わせが見つかりません")

        # 更新データを構築
        update_data = {}
        if status is not None:
            update_data["status"] = status
        if assigned_staff_id is not None:
            update_data["assigned_staff_id"] = assigned_staff_id
        if priority is not None:
            update_data["priority"] = priority
        if admin_notes is not None:
            update_data["admin_notes"] = admin_notes

        if not update_data:
            # 更新データがない場合は現在のデータを返す
            return inquiry

        # updated_at を更新
        update_data["updated_at"] = datetime.now(timezone.utc)

        # ORM経由で更新（よりSQLAlchemyのベストプラクティスに沿った方法）
        for key, value in update_data.items():
            setattr(inquiry, key, value)

        db.add(inquiry)
        await db.flush()
        await db.refresh(inquiry, ["message", "assigned_staff"])

        return inquiry

    async def delete_inquiry(
        self,
        db: AsyncSession,
        *,
        inquiry_id: UUID
    ) -> bool:
        """
        問い合わせを削除

        Args:
            db: データベースセッション
            inquiry_id: 問い合わせID

        Returns:
            削除成功: True, 対象が存在しない: False

        Note:
            - InquiryDetail を削除すると CASCADE により Message も削除される
            - Message が削除されると CASCADE により MessageRecipient も削除される
        """
        # 対象を取得
        inquiry = await self.get_inquiry_by_id(db=db, inquiry_id=inquiry_id)
        if inquiry is None:
            return False

        # Message を削除（CASCADE により InquiryDetail も削除される）
        stmt = delete(Message).where(Message.id == inquiry.message_id)
        await db.execute(stmt)
        await db.flush()

        return True

    async def append_delivery_log(
        self,
        db: AsyncSession,
        *,
        inquiry_detail_id: UUID,
        log_entry: dict
    ) -> InquiryDetail:
        """
        delivery_logにエントリを追加

        Args:
            db: データベースセッション
            inquiry_detail_id: InquiryDetailのID
            log_entry: 追加するログエントリ

        Returns:
            更新された InquiryDetail

        Raises:
            ValueError: 問い合わせが見つからない場合
        """
        inquiry = await self.get_inquiry_by_id(db=db, inquiry_id=inquiry_detail_id)
        if not inquiry:
            raise ValueError("問い合わせが見つかりません")

        # delivery_logを取得または初期化（新しいリストとしてコピー）
        current_log = list(inquiry.delivery_log) if inquiry.delivery_log else []

        # 新しいログエントリを追加
        current_log.append(log_entry)

        # JSONフィールドを更新（新しいリストを割り当てることで変更を検出させる）
        inquiry.delivery_log = current_log
        inquiry.updated_at = datetime.now(timezone.utc)

        # SQLAlchemyにJSONフィールドの変更を明示的に通知
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(inquiry, "delivery_log")

        db.add(inquiry)
        await db.flush()
        await db.refresh(inquiry)

        return inquiry


# グローバルインスタンス
crud_inquiry = CRUDInquiry(InquiryDetail)
inquiry_detail = crud_inquiry  # email_utils.py からの参照用エイリアス
