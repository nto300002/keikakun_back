"""
統合型監査ログ CRUD操作

フィルタページネーション（Option A）とカーソルページネーション（Option B）の両方をサポート
"""
import uuid
import datetime
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.staff_profile import AuditLog


# アクション別の保持期間設定（日数）
RETENTION_POLICIES = {
    # 法的要件: 5年
    "legal": {
        "days": 1825,  # 5年
        "actions": [
            "withdrawal.approved",
            "withdrawal.executed",
            "staff.deleted",
            "office.deleted",
            "terms.agreed",
        ]
    },
    # 重要操作: 3年
    "important": {
        "days": 1095,  # 3年
        "actions": [
            "staff.created",
            "staff.role_changed",
            "office.created",
            "office.updated",
            "withdrawal.requested",
            "withdrawal.rejected",
        ]
    },
    # 一般操作: 1年
    "standard": {
        "days": 365,  # 1年
        "actions": [
            "staff.updated",
            "staff.password_changed",
            "profile.updated",
            "profile.email_changed",
        ]
    },
    # 短期: 90日
    "short_term": {
        "days": 90,
        "actions": [
            "staff.login",
            "staff.logout",
            "mfa.enabled",
            "mfa.disabled",
        ]
    },
}


class CRUDAuditLog(CRUDBase[AuditLog, Dict[str, Any], Dict[str, Any]]):
    """
    統合型監査ログのCRUD操作

    提供機能:
    - create_log: 監査ログ作成
    - get_logs: フィルタベースページネーション（Option A）
    - get_logs_cursor: カーソルベースページネーション（Option B）
    - get_logs_by_target: 特定リソースの監査ログ取得
    - get_admin_important_logs: app_admin向け重要アクションフィルタリング
    - cleanup_old_logs: 保持期間ベースの古いログ削除
    """

    async def create_log(
        self,
        db: AsyncSession,
        *,
        actor_id: Optional[uuid.UUID] = None,
        action: str,
        target_type: str,
        target_id: Optional[uuid.UUID] = None,
        office_id: Optional[uuid.UUID] = None,
        actor_role: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[dict] = None,
        is_test_data: bool = False,
        auto_commit: bool = True
    ) -> AuditLog:
        """
        監査ログを作成

        Args:
            db: データベースセッション
            actor_id: 操作実行者のスタッフID（システムによる自動処理の場合はNone）
            action: アクション種別（"staff.deleted", "withdrawal.approved" など）
            target_type: 対象リソースタイプ（"staff", "office", "withdrawal_request" など）
            target_id: 対象リソースのID
            office_id: 事務所ID（横断検索用）
            actor_role: 実行時のロール（システム処理の場合は"system"）
            ip_address: 操作元のIPアドレス
            user_agent: 操作元のUser-Agent
            details: 操作の詳細情報（JSON形式）
            is_test_data: テストデータフラグ
            auto_commit: 自動コミット（デフォルト: True）

        Returns:
            作成された監査ログ

        Note:
            - auto_commit=Falseの場合、トランザクション管理は呼び出し側で行う
            - actor_id=Noneの場合、システムによる自動処理として記録される
        """
        audit_log = AuditLog(
            staff_id=actor_id,
            actor_role=actor_role or ("system" if actor_id is None else None),
            action=action,
            target_type=target_type,
            target_id=target_id,
            office_id=office_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
            is_test_data=is_test_data
        )

        db.add(audit_log)

        if auto_commit:
            await db.commit()
            await db.refresh(audit_log)
        else:
            await db.flush()

        return audit_log

    async def get_logs(
        self,
        db: AsyncSession,
        *,
        office_id: Optional[uuid.UUID] = None,
        target_type: Optional[str] = None,
        action: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
        target_id: Optional[uuid.UUID] = None,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        skip: int = 0,
        limit: int = 50,
        include_test_data: bool = False
    ) -> Tuple[List[AuditLog], int]:
        """
        フィルタベースページネーション（Option A）

        複合条件でのフィルタリングとオフセットベースのページネーションを提供

        Args:
            db: データベースセッション
            office_id: 事務所IDでフィルタ
            target_type: 対象タイプでフィルタ（"staff", "office" など）
            action: アクションでフィルタ（部分一致）
            actor_id: 操作実行者でフィルタ
            target_id: 対象リソースIDでフィルタ
            start_date: 開始日時
            end_date: 終了日時
            skip: スキップする件数
            limit: 取得する最大件数
            include_test_data: テストデータを含めるか

        Returns:
            (監査ログリスト, 総件数)のタプル
        """
        # 基本クエリ
        conditions = []

        if not include_test_data:
            conditions.append(AuditLog.is_test_data == False)  # noqa: E712

        if office_id:
            conditions.append(AuditLog.office_id == office_id)

        if target_type:
            conditions.append(AuditLog.target_type == target_type)

        if action:
            conditions.append(AuditLog.action.ilike(f"%{action}%"))

        if actor_id:
            conditions.append(AuditLog.staff_id == actor_id)

        if target_id:
            conditions.append(AuditLog.target_id == target_id)

        if start_date:
            conditions.append(AuditLog.timestamp >= start_date)

        if end_date:
            conditions.append(AuditLog.timestamp <= end_date)

        where_clause = and_(*conditions) if conditions else True

        # カウントクエリ
        count_query = select(func.count()).select_from(AuditLog).where(where_clause)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # データ取得クエリ
        query = (
            select(AuditLog)
            .where(where_clause)
            .order_by(AuditLog.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        logs = list(result.scalars().all())

        return logs, total

    async def get_logs_cursor(
        self,
        db: AsyncSession,
        *,
        office_id: Optional[uuid.UUID] = None,
        target_type: Optional[str] = None,
        cursor: Optional[datetime.datetime] = None,
        limit: int = 50,
        include_test_data: bool = False
    ) -> Tuple[List[AuditLog], Optional[datetime.datetime]]:
        """
        カーソルベースページネーション（Option B）

        無限スクロールやリアルタイム更新に適したカーソルベースのページネーション

        Args:
            db: データベースセッション
            office_id: 事務所IDでフィルタ
            target_type: 対象タイプでフィルタ
            cursor: カーソル（前回取得した最後のtimestamp）
            limit: 取得する最大件数
            include_test_data: テストデータを含めるか

        Returns:
            (監査ログリスト, 次のカーソル)のタプル
            次のカーソルがNoneの場合、これ以上データがない
        """
        conditions = []

        if not include_test_data:
            conditions.append(AuditLog.is_test_data == False)  # noqa: E712

        if office_id:
            conditions.append(AuditLog.office_id == office_id)

        if target_type:
            conditions.append(AuditLog.target_type == target_type)

        if cursor:
            conditions.append(AuditLog.timestamp < cursor)

        where_clause = and_(*conditions) if conditions else True

        query = (
            select(AuditLog)
            .where(where_clause)
            .order_by(AuditLog.timestamp.desc())
            .limit(limit + 1)  # 次ページの有無を確認するため+1
        )
        result = await db.execute(query)
        logs = list(result.scalars().all())

        # 次のカーソルを計算
        next_cursor = None
        if len(logs) > limit:
            logs = logs[:limit]
            next_cursor = logs[-1].timestamp if logs else None

        return logs, next_cursor

    async def get_logs_by_target(
        self,
        db: AsyncSession,
        *,
        target_type: str,
        target_id: uuid.UUID,
        limit: int = 100,
        include_test_data: bool = False
    ) -> List[AuditLog]:
        """
        特定のリソースに対する監査ログを取得

        Args:
            db: データベースセッション
            target_type: 対象タイプ
            target_id: 対象リソースID
            limit: 取得する最大件数
            include_test_data: テストデータを含めるか

        Returns:
            監査ログリスト（新しい順）
        """
        conditions = [
            AuditLog.target_type == target_type,
            AuditLog.target_id == target_id,
        ]

        if not include_test_data:
            conditions.append(AuditLog.is_test_data == False)  # noqa: E712

        query = (
            select(AuditLog)
            .where(and_(*conditions))
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_admin_important_logs(
        self,
        db: AsyncSession,
        *,
        actions: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 50,
        include_test_data: bool = False
    ) -> Tuple[List[AuditLog], int]:
        """
        app_admin向けの重要アクションフィルタリング

        デフォルトで以下のactionをフィルタ：
        - staff.deleted: スタッフ削除
        - office.updated: 事務所情報更新
        - withdrawal.approved: 退会承認
        - terms.agreed: 利用規約同意

        Args:
            db: データベースセッション
            actions: フィルタリングするアクションリスト（Noneの場合はデフォルト）
            skip: スキップする件数
            limit: 取得する最大件数（デフォルト50件）
            include_test_data: テストデータを含めるか

        Returns:
            (監査ログリスト, 総件数)のタプル
        """
        # デフォルトの重要アクション
        if actions is None:
            actions = [
                "staff.deleted",
                "office.updated",
                "withdrawal.approved",
                "terms.agreed"
            ]

        # 基本条件
        conditions = [
            AuditLog.action.in_(actions)
        ]

        if not include_test_data:
            conditions.append(AuditLog.is_test_data == False)  # noqa: E712

        where_clause = and_(*conditions) if conditions else True

        # カウントクエリ
        count_query = select(func.count()).select_from(AuditLog).where(where_clause)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # データ取得クエリ
        query = (
            select(AuditLog)
            .where(where_clause)
            .order_by(AuditLog.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        logs = list(result.scalars().all())

        return logs, total

    async def cleanup_old_logs(
        self,
        db: AsyncSession,
        *,
        batch_size: int = 1000,
        dry_run: bool = False
    ) -> Dict[str, int]:
        """
        保持期間ベースの古いログ削除

        アクション種別ごとに異なる保持期間を適用:
        - 法的要件: 5年（退会承認、削除操作、規約同意など）
        - 重要操作: 3年（作成、ロール変更など）
        - 一般操作: 1年（更新、パスワード変更など）
        - 短期: 90日（ログイン、ログアウトなど）

        Args:
            db: データベースセッション
            batch_size: 一度に削除する最大件数
            dry_run: Trueの場合、削除対象件数のみ返す（実際には削除しない）

        Returns:
            カテゴリ別の削除件数
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        deleted_counts = {}

        for category, policy in RETENTION_POLICIES.items():
            retention_days = policy["days"]
            actions = policy["actions"]
            cutoff_date = now - datetime.timedelta(days=retention_days)

            # 削除対象のカウント
            count_query = (
                select(func.count())
                .select_from(AuditLog)
                .where(
                    and_(
                        AuditLog.action.in_(actions),
                        AuditLog.timestamp < cutoff_date
                    )
                )
            )
            count_result = await db.execute(count_query)
            count = count_result.scalar() or 0

            deleted_counts[category] = count

            if not dry_run and count > 0:
                # バッチ削除
                delete_query = (
                    delete(AuditLog)
                    .where(
                        and_(
                            AuditLog.action.in_(actions),
                            AuditLog.timestamp < cutoff_date
                        )
                    )
                )
                await db.execute(delete_query)

        # 未分類のアクションは標準保持期間（1年）を適用
        all_categorized_actions = []
        for policy in RETENTION_POLICIES.values():
            all_categorized_actions.extend(policy["actions"])

        standard_cutoff = now - datetime.timedelta(days=365)

        uncategorized_count_query = (
            select(func.count())
            .select_from(AuditLog)
            .where(
                and_(
                    ~AuditLog.action.in_(all_categorized_actions),
                    AuditLog.timestamp < standard_cutoff
                )
            )
        )
        uncategorized_count_result = await db.execute(uncategorized_count_query)
        uncategorized_count = uncategorized_count_result.scalar() or 0

        deleted_counts["uncategorized"] = uncategorized_count

        if not dry_run and uncategorized_count > 0:
            delete_uncategorized_query = (
                delete(AuditLog)
                .where(
                    and_(
                        ~AuditLog.action.in_(all_categorized_actions),
                        AuditLog.timestamp < standard_cutoff
                    )
                )
            )
            await db.execute(delete_uncategorized_query)

        if not dry_run:
            await db.flush()

        return deleted_counts


# インスタンス化
audit_log = CRUDAuditLog(AuditLog)
