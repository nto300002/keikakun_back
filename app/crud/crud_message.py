"""
メッセージCRUD操作

個別メッセージ、一斉通知、受信箱、統計などの操作を提供
トランザクション管理とバルクインサートを適切に実装
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update, func, and_, Integer, delete
from sqlalchemy.exc import IntegrityError

from app.crud.base import CRUDBase
from app.models.message import Message, MessageRecipient
from app.models.enums import MessageType, MessagePriority


class CRUDMessage(CRUDBase[Message, Dict[str, Any], Dict[str, Any]]):

    async def create_personal_message(
        self,
        db: AsyncSession,
        *,
        obj_in: Dict[str, Any]
    ) -> Message:
        """
        個別メッセージを作成

        Args:
            db: データベースセッション
            obj_in: メッセージデータ（sender_staff_id, office_id, recipient_ids, title, content等）

        Returns:
            作成されたメッセージ（受信者情報を含む）

        Note:
            - 1トランザクションでメッセージ本体と受信者を作成
            - 重複した受信者IDは自動的に除外
            - commitはエンドポイントで行う（auto_commit=False）
        """
        # 受信者IDの重複を除去
        recipient_ids = list(set(obj_in.get("recipient_ids", [])))

        if not recipient_ids:
            raise ValueError("受信者が指定されていません")

        # メッセージ本体を作成
        message = Message(
            sender_staff_id=obj_in["sender_staff_id"],
            office_id=obj_in["office_id"],
            message_type=obj_in.get("message_type", MessageType.personal),
            priority=obj_in.get("priority", MessagePriority.normal),
            title=obj_in["title"],
            content=obj_in["content"]
        )
        db.add(message)
        await db.flush()  # messageのIDを取得するためflush

        # 受信者レコードを作成（バルクインサート）
        recipients = [
            MessageRecipient(
                message_id=message.id,
                recipient_staff_id=recipient_id,
                is_read=False,
                is_archived=False
            )
            for recipient_id in recipient_ids
        ]

        db.add_all(recipients)
        await db.flush()

        # リレーションシップをロード
        await db.refresh(message, ["recipients"])

        return message

    async def create_personal_message_with_limit(
        self,
        db: AsyncSession,
        *,
        sender_staff_id: UUID,
        recipient_staff_ids: List[UUID],
        office_id: UUID,
        title: str,
        body: str,
        priority: str = "normal",
        limit: int = 50
    ) -> Message:
        """
        個別メッセージを作成（事務所ごとのメッセージ数上限機能付き）

        Args:
            db: データベースセッション
            sender_staff_id: 送信者スタッフID
            recipient_staff_ids: 受信者スタッフIDリスト
            office_id: 事務所ID
            title: メッセージタイトル
            body: メッセージ本文
            priority: 優先度（normal, high, urgent）
            limit: 事務所ごとのメッセージ数上限（デフォルト50件）

        Returns:
            作成されたメッセージ

        Note:
            - 事務所のメッセージ数がlimitを超える場合、古いメッセージから自動削除
            - is_test_data=Trueのメッセージは上限カウント対象外
            - commitはエンドポイントで行う
        """
        # 現在の事務所のメッセージ数をカウント（テストデータを除外）
        count_stmt = select(func.count(Message.id)).where(
            Message.office_id == office_id,
            Message.is_test_data == False
        )
        result = await db.execute(count_stmt)
        current_count = result.scalar()

        # 上限チェック: 現在の数が上限以上なら古いメッセージを削除
        if current_count >= limit:
            # 削除すべきメッセージ数を計算
            delete_count = current_count - limit + 1

            # 最も古いメッセージのIDを取得（created_atが同じ場合はidでソート）
            oldest_ids_stmt = (
                select(Message.id)
                .where(
                    Message.office_id == office_id,
                    Message.is_test_data == False
                )
                .order_by(Message.created_at.asc(), Message.id.asc())
                .limit(delete_count)
            )
            oldest_ids_result = await db.execute(oldest_ids_stmt)
            oldest_ids = [row[0] for row in oldest_ids_result.all()]

            # 古いメッセージを削除
            if oldest_ids:
                delete_stmt = delete(Message).where(Message.id.in_(oldest_ids))
                await db.execute(delete_stmt)
                await db.flush()
                # セッションキャッシュをクリアして、削除が確実に反映されるようにする
                db.expire_all()

        # 新しいメッセージを作成（既存のメソッドを使用）
        obj_in = {
            "sender_staff_id": sender_staff_id,
            "recipient_ids": recipient_staff_ids,
            "office_id": office_id,
            "title": title,
            "content": body,  # bodyをcontentに変換
            "message_type": MessageType.personal,
            "priority": priority
        }

        new_message = await self.create_personal_message(db=db, obj_in=obj_in)

        return new_message

    async def create_announcement(
        self,
        db: AsyncSession,
        *,
        obj_in: Dict[str, Any]
    ) -> Message:
        """
        一斉通知を作成（バルクインサート）

        Args:
            db: データベースセッション
            obj_in: 一斉通知データ

        Returns:
            作成されたメッセージ

        Note:
            - 大量の受信者に対応するためバルクインサートを使用
            - 受信者が500件以上の場合はチャンク処理を行う
            - commitはエンドポイントで行う
        """
        recipient_ids = list(set(obj_in.get("recipient_ids", [])))

        if not recipient_ids:
            raise ValueError("受信者が指定されていません")

        # メッセージ本体を作成
        message = Message(
            sender_staff_id=obj_in["sender_staff_id"],
            office_id=obj_in["office_id"],
            message_type=MessageType.announcement,
            priority=obj_in.get("priority", MessagePriority.normal),
            title=obj_in["title"],
            content=obj_in["content"]
        )
        db.add(message)
        await db.flush()

        # 大量受信者の場合はチャンク処理
        chunk_size = 500
        total_recipients = len(recipient_ids)

        for i in range(0, total_recipients, chunk_size):
            chunk = recipient_ids[i:i + chunk_size]
            recipients = [
                MessageRecipient(
                    message_id=message.id,
                    recipient_staff_id=recipient_id,
                    is_read=False,
                    is_archived=False
                )
                for recipient_id in chunk
            ]
            db.add_all(recipients)
            await db.flush()

        # リレーションシップをロード
        await db.refresh(message, ["recipients"])

        return message

    async def get_inbox_messages(
        self,
        db: AsyncSession,
        *,
        recipient_staff_id: UUID,
        message_type: Optional[MessageType] = None,
        is_read: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Message]:
        """
        受信箱のメッセージ一覧を取得

        Args:
            db: データベースセッション
            recipient_staff_id: 受信者スタッフID
            message_type: メッセージタイプでフィルタ（オプション）
            is_read: 既読状態でフィルタ（オプション）
            skip: スキップ数
            limit: 取得数上限

        Returns:
            メッセージ一覧
        """
        # MessageRecipientを経由してMessageを取得
        stmt = (
            select(Message)
            .join(MessageRecipient)
            .where(MessageRecipient.recipient_staff_id == recipient_staff_id)
            .options(selectinload(Message.recipients), selectinload(Message.sender))
            .order_by(Message.created_at.desc())
        )

        # フィルタを適用
        if message_type is not None:
            stmt = stmt.where(Message.message_type == message_type)

        if is_read is not None:
            stmt = stmt.where(MessageRecipient.is_read == is_read)

        stmt = stmt.offset(skip).limit(limit)

        result = await db.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_unread_messages(
        self,
        db: AsyncSession,
        *,
        recipient_staff_id: UUID
    ) -> List[Message]:
        """
        未読メッセージのみ取得

        Args:
            db: データベースセッション
            recipient_staff_id: 受信者スタッフID

        Returns:
            未読メッセージ一覧
        """
        return await self.get_inbox_messages(
            db=db,
            recipient_staff_id=recipient_staff_id,
            is_read=False
        )

    async def mark_as_read(
        self,
        db: AsyncSession,
        *,
        message_id: UUID,
        recipient_staff_id: UUID
    ) -> MessageRecipient:
        """
        メッセージを既読にする

        Args:
            db: データベースセッション
            message_id: メッセージID
            recipient_staff_id: 受信者スタッフID

        Returns:
            更新された受信者レコード

        Raises:
            ValueError: 受信者レコードが見つからない場合
        """
        stmt = (
            select(MessageRecipient)
            .where(
                and_(
                    MessageRecipient.message_id == message_id,
                    MessageRecipient.recipient_staff_id == recipient_staff_id
                )
            )
        )

        result = await db.execute(stmt)
        recipient = result.scalar_one_or_none()

        if not recipient:
            raise ValueError("メッセージ受信者が見つかりません")

        # 既読化
        recipient.is_read = True
        recipient.read_at = datetime.now(timezone.utc)

        db.add(recipient)
        await db.flush()

        return recipient

    async def get_message_stats(
        self,
        db: AsyncSession,
        *,
        message_id: UUID
    ) -> Dict[str, Any]:
        """
        メッセージの統計情報を取得

        Args:
            db: データベースセッション
            message_id: メッセージID

        Returns:
            統計情報（total_recipients, read_count, unread_count, read_rate）
        """
        # 総受信者数と既読数を集計
        stmt = (
            select(
                func.count(MessageRecipient.id).label("total"),
                func.sum(func.cast(MessageRecipient.is_read, Integer)).label("read_count")
            )
            .where(MessageRecipient.message_id == message_id)
        )

        result = await db.execute(stmt)
        row = result.first()

        total_recipients = row.total if row.total else 0
        read_count = int(row.read_count) if row.read_count else 0
        unread_count = total_recipients - read_count
        read_rate = (read_count / total_recipients * 100) if total_recipients > 0 else 0.0

        return {
            "total_recipients": total_recipients,
            "read_count": read_count,
            "unread_count": unread_count,
            "read_rate": round(read_rate, 2)
        }

    async def get_unread_count(
        self,
        db: AsyncSession,
        *,
        recipient_staff_id: UUID
    ) -> int:
        """
        受信者の未読メッセージ件数を取得

        Args:
            db: データベースセッション
            recipient_staff_id: 受信者スタッフID

        Returns:
            未読件数
        """
        stmt = (
            select(func.count(MessageRecipient.id))
            .where(
                and_(
                    MessageRecipient.recipient_staff_id == recipient_staff_id,
                    MessageRecipient.is_read == False
                )
            )
        )

        result = await db.execute(stmt)
        count = result.scalar()

        return count if count else 0

    async def get_message_by_id(
        self,
        db: AsyncSession,
        *,
        message_id: UUID
    ) -> Optional[Message]:
        """
        メッセージIDでメッセージを取得

        Args:
            db: データベースセッション
            message_id: メッセージID

        Returns:
            メッセージ（受信者情報、送信者情報を含む）
        """
        stmt = (
            select(Message)
            .where(Message.id == message_id)
            .options(selectinload(Message.recipients), selectinload(Message.sender))
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_all_as_read(
        self,
        db: AsyncSession,
        *,
        recipient_staff_id: UUID
    ) -> int:
        """
        受信者の全未読メッセージを既読にする

        Args:
            db: データベースセッション
            recipient_staff_id: 受信者スタッフID

        Returns:
            更新件数
        """
        stmt = (
            update(MessageRecipient)
            .where(
                and_(
                    MessageRecipient.recipient_staff_id == recipient_staff_id,
                    MessageRecipient.is_read == False
                )
            )
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )

        result = await db.execute(stmt)
        await db.flush()

        return result.rowcount

    async def archive_message(
        self,
        db: AsyncSession,
        *,
        message_id: UUID,
        recipient_staff_id: UUID,
        is_archived: bool = True
    ) -> MessageRecipient:
        """
        メッセージをアーカイブする

        Args:
            db: データベースセッション
            message_id: メッセージID
            recipient_staff_id: 受信者スタッフID
            is_archived: アーカイブ状態

        Returns:
            更新された受信者レコード
        """
        stmt = (
            select(MessageRecipient)
            .where(
                and_(
                    MessageRecipient.message_id == message_id,
                    MessageRecipient.recipient_staff_id == recipient_staff_id
                )
            )
        )

        result = await db.execute(stmt)
        recipient = result.scalar_one_or_none()

        if not recipient:
            raise ValueError("メッセージ受信者が見つかりません")

        recipient.is_archived = is_archived
        db.add(recipient)
        await db.flush()

        return recipient


# インスタンス化
crud_message = CRUDMessage(Message)
