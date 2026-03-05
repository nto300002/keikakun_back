"""スタッフプロフィール関連のサービス"""
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from passlib.context import CryptContext
from fastapi import HTTPException, status

from app.models.staff import Staff
from app.models.staff_profile import AuditLog, EmailChangeRequest as EmailChangeRequestModel, PasswordHistory
from app.schemas.staff_profile import StaffNameUpdate, PasswordChange, EmailChangeRequest
from app.core.security import verify_password, get_password_hash
from app.core import mail
from app.messages import ja

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class RateLimitExceededError(Exception):
    """レート制限超過エラー"""
    pass


class StaffProfileService:
    """スタッフプロフィール管理サービス"""

    async def update_name(
        self,
        db: AsyncSession,
        staff_id: str,
        name_data: StaffNameUpdate
    ) -> Staff:
        """
        スタッフの名前を更新する

        手順:
        1. バリデーション（Pydanticで実施済み）
        2. データの正規化（Pydanticで実施済み）
        3. スタッフ情報の取得
        4. 更新
        5. full_name の計算
        6. 変更履歴の記録
        """
        # スタッフ情報の取得
        stmt = select(Staff).where(Staff.id == staff_id)
        result = await db.execute(stmt)
        staff = result.scalar_one_or_none()

        if not staff:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.STAFF_NOT_FOUND
            )

        # 古い名前を保存
        old_name = f"{staff.last_name or ''} {staff.first_name or ''}".strip()

        try:
            # 更新
            staff.last_name = name_data.last_name
            staff.first_name = name_data.first_name
            staff.last_name_furigana = name_data.last_name_furigana
            staff.first_name_furigana = name_data.first_name_furigana
            staff.full_name = f"{name_data.last_name} {name_data.first_name}"
            staff.updated_at = datetime.now(timezone.utc)

            await db.flush()
            await db.refresh(staff)

            # 変更履歴の記録
            await self._log_name_change(
                db,
                staff_id=staff_id,
                old_name=old_name,
                new_name=staff.full_name
            )

            await db.commit()
            return staff

        except Exception as e:
            await db.rollback()
            raise

    async def _log_name_change(
        self,
        db: AsyncSession,
        staff_id: str,
        old_name: str,
        new_name: str
    ) -> None:
        """名前変更の監査ログ記録"""
        audit_log = AuditLog(
            staff_id=staff_id,
            action="UPDATE_NAME",
            old_value=old_name,
            new_value=new_name,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.flush()

    async def change_password(
        self,
        db: AsyncSession,
        staff_id: str,
        password_change: PasswordChange
    ) -> Dict[str, any]:
        """
        パスワード変更

        手順:
        1. 入力値の基本検証（Pydanticで実施済み）
        2. レート制限チェック
        3. パスワード変更のメインロジックを実行（try-finallyで試行を記録）
        4. 現在のパスワード確認
        5. 新しいパスワードの一致確認
        6. パスワード履歴チェック
        7. パスワードのハッシュ化と保存
        8. パスワード履歴の更新
        9. 監査ログ記録（成功時）
        """
        # スタッフ情報取得
        stmt = select(Staff).where(Staff.id == staff_id)
        result = await db.execute(stmt)
        staff = result.scalar_one_or_none()

        if not staff:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.STAFF_NOT_FOUND
            )

        # レート制限チェック（1時間に3回まで）
        await self._check_password_change_rate_limit(db, staff_id)

        # パスワード変更のメインロジック（try-finallyで試行を記録）
        exception_to_raise = None
        updated_at = None  # MissingGreenletエラー対策: commit前に取得するため

        # 新パスワードの一致確認（DB操作なし。savepoint外で先行チェック）
        if password_change.new_password != password_change.new_password_confirm:
            exception_to_raise = HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.STAFF_PASSWORD_MISMATCH
            )

        # 現在のパスワード確認（DB操作なし。savepoint外で先行チェック）
        if exception_to_raise is None and not pwd_context.verify(
            password_change.current_password, staff.hashed_password
        ):
            # 失敗回数をカウント（総当たり攻撃対策。savepoint外でコミット対象にする）
            await self._increment_failed_password_attempts_sync(db, staff)
            exception_to_raise = HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.STAFF_CURRENT_PASSWORD_INCORRECT
            )

        if exception_to_raise is None:
            # DB変更操作をセーブポイントで囲む（失敗時は変更のみロールバック）
            try:
                async with db.begin_nested():
                    # パスワード履歴チェック
                    await self._check_password_history(db, staff_id, password_change.new_password)

                    # ユーザー情報との類似性チェック
                    self._check_password_similarity(password_change.new_password, staff)

                    # パスワードのハッシュ化
                    hashed_password = pwd_context.hash(password_change.new_password)

                    # データベース更新
                    staff.hashed_password = hashed_password
                    staff.password_changed_at = datetime.now(timezone.utc)
                    staff.failed_password_attempts = 0  # リセット
                    staff.updated_at = datetime.now(timezone.utc)

                    await db.flush()

                    # パスワード履歴に追加
                    password_history = PasswordHistory(
                        staff_id=staff_id,
                        hashed_password=hashed_password,
                        changed_at=datetime.now(timezone.utc)
                    )
                    db.add(password_history)
                    await db.flush()

                    # 古い履歴の削除（最新3件のみ保持）
                    await self._cleanup_password_history(db, staff_id, keep_recent=3)

                    # 監査ログ
                    await self._log_password_change(db, staff_id)

                    # パスワード変更通知メール送信
                    staff_name = staff.full_name
                    try:
                        await mail.send_password_changed_notification(
                            email=staff.email,
                            staff_name=staff_name
                        )
                    except Exception as mail_err:
                        # メール送信失敗はログに記録するが、処理は続行
                        print(f"パスワード変更通知メール送信失敗: {mail_err}")

                    # commit前にupdated_atを取得（MissingGreenletエラー対策）
                    updated_at = staff.updated_at

            except Exception as e:
                # セーブポイントのロールバックは begin_nested が自動処理済み
                exception_to_raise = e

        # 成功でも失敗でも試行を記録してコミット（外部トランザクションは常に有効）
        await self._log_password_change_attempt(db, staff_id)
        await db.commit()

        # エラーが発生していた場合は再raiseする
        if exception_to_raise:
            raise exception_to_raise

        return {
            "message": "パスワードを変更しました",
            "updated_at": updated_at,
            "logged_out_devices": 0  # 今後のセッション管理で実装
        }

    def _check_password_similarity(
        self,
        password: str,
        staff: Staff
    ) -> None:
        """ユーザー情報との類似性チェック"""
        password_lower = password.lower()

        # メールアドレスのローカル部分
        email_local = staff.email.split('@')[0].lower()
        if email_local in password_lower:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.STAFF_PASSWORD_CONTAINS_EMAIL
            )

        # 名前
        if staff.last_name and staff.last_name.lower() in password_lower:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.STAFF_PASSWORD_CONTAINS_NAME
            )
        if staff.first_name and staff.first_name.lower() in password_lower:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.STAFF_PASSWORD_CONTAINS_NAME
            )

    async def _check_password_history(
        self,
        db: AsyncSession,
        staff_id: str,
        new_password: str
    ) -> None:
        """過去のパスワードとの重複チェック"""
        # 過去3件のパスワード履歴を取得
        stmt = (
            select(PasswordHistory)
            .where(PasswordHistory.staff_id == staff_id)
            .order_by(PasswordHistory.changed_at.desc())
            .limit(3)
        )
        result = await db.execute(stmt)
        history = result.scalars().all()

        for record in history:
            if pwd_context.verify(new_password, record.hashed_password):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="過去に使用したパスワードは使用できません。別のパスワードを設定してください。"
                )

    async def _cleanup_password_history(
        self,
        db: AsyncSession,
        staff_id: str,
        keep_recent: int = 3
    ) -> None:
        """古いパスワード履歴を削除（最新N件のみ保持）"""
        # 最新N件のIDを取得
        stmt_keep = (
            select(PasswordHistory.id)
            .where(PasswordHistory.staff_id == staff_id)
            .order_by(PasswordHistory.changed_at.desc())
            .limit(keep_recent)
        )
        result = await db.execute(stmt_keep)
        keep_ids = [row[0] for row in result.all()]

        # 最新N件以外を削除
        if keep_ids:
            stmt_delete = delete(PasswordHistory).where(
                PasswordHistory.staff_id == staff_id,
                PasswordHistory.id.notin_(keep_ids)
            )
            await db.execute(stmt_delete)
            await db.flush()

    async def _increment_failed_password_attempts(
        self,
        db: AsyncSession,
        staff: Staff
    ) -> None:
        """パスワード失敗回数のカウント（廃止予定）"""
        await self._increment_failed_password_attempts_sync(db, staff)

    async def _increment_failed_password_attempts_sync(
        self,
        db: AsyncSession,
        staff: Staff
    ) -> None:
        """
        パスワード失敗回数のカウント

        現在のセッションで更新します。
        エラー発生時は親トランザクションでコミットされます。
        """
        # 失敗回数をインクリメント
        staff.failed_password_attempts = (staff.failed_password_attempts or 0) + 1

        # 5回失敗でアカウントロック
        if staff.failed_password_attempts >= 5:
            staff.is_locked = True
            staff.locked_at = datetime.now(timezone.utc)

        await db.flush()

    async def _log_password_change(
        self,
        db: AsyncSession,
        staff_id: str
    ) -> None:
        """パスワード変更成功の監査ログ記録"""
        audit_log = AuditLog(
            staff_id=staff_id,
            action="CHANGE_PASSWORD",
            old_value=None,  # セキュリティのためパスワードは記録しない
            new_value=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.flush()

    async def _log_password_change_attempt(
        self,
        db: AsyncSession,
        staff_id: str
    ) -> None:
        """
        パスワード変更試行の記録（成功・失敗に関わらず）

        現在のセッションで記録します。
        finallyブロックで呼ばれるため、エラー発生時も確実にコミットされます。
        """
        audit_log = AuditLog(
            staff_id=staff_id,
            action="ATTEMPT_CHANGE_PASSWORD",
            old_value=None,
            new_value=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.flush()

    async def _check_password_change_rate_limit(
        self,
        db: AsyncSession,
        staff_id: str,
        max_attempts: int = 3,
        time_window_hours: int = 1
    ) -> None:
        """
        パスワード変更のレート制限チェック

        Args:
            db: データベースセッション
            staff_id: スタッフID
            max_attempts: 制限時間内の最大試行回数（デフォルト: 3回）
            time_window_hours: 制限時間（時間単位、デフォルト: 1時間）

        Raises:
            RateLimitExceededError: レート制限を超えた場合
        """
        # 指定時間内のパスワード変更試行回数をカウント
        time_threshold = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)

        stmt = (
            select(func.count(AuditLog.id))
            .where(
                AuditLog.staff_id == staff_id,
                AuditLog.action == "ATTEMPT_CHANGE_PASSWORD",
                AuditLog.timestamp >= time_threshold
            )
        )
        result = await db.execute(stmt)
        attempt_count = result.scalar()

        if attempt_count >= max_attempts:
            raise RateLimitExceededError(
                f"パスワード変更の試行回数が上限に達しました。"
                f"{time_window_hours}時間後に再度お試しください。"
            )


    async def request_email_change(
        self,
        db: AsyncSession,
        staff_id: str,
        email_request: EmailChangeRequest
    ) -> Dict[str, any]:
        """
        メールアドレス変更リクエストを作成

        手順:
        1. スタッフ情報取得
        2. パスワード確認
        3. レート制限チェック（24時間以内に3回まで）
        4. 新しいメールアドレスの重複チェック
        5. 確認トークン生成
        6. リクエストレコード作成
        7. 確認メール送信（新旧両方のアドレス）
        """
        # スタッフ情報取得
        stmt = select(Staff).where(Staff.id == staff_id)
        result = await db.execute(stmt)
        staff = result.scalar_one_or_none()

        if not staff:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.STAFF_NOT_FOUND
            )

        # パスワード確認
        if not pwd_context.verify(email_request.password, staff.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.STAFF_CURRENT_PASSWORD_INCORRECT
            )

        # レート制限チェック（24時間以内に3回まで）
        time_threshold = datetime.now(timezone.utc) - timedelta(hours=24)
        stmt_count = (
            select(func.count(EmailChangeRequestModel.id))
            .where(
                EmailChangeRequestModel.staff_id == staff_id,
                EmailChangeRequestModel.created_at >= time_threshold
            )
        )
        result_count = await db.execute(stmt_count)
        request_count = result_count.scalar()

        if request_count >= 3:
            raise RateLimitExceededError(
                "メールアドレスの変更回数が上限に達しています。24時間後に再度お試しください。"
            )

        # 新しいメールアドレスの重複チェック
        stmt_email = select(Staff).where(Staff.email == email_request.new_email)
        result_email = await db.execute(stmt_email)
        existing_staff = result_email.scalar_one_or_none()

        if existing_staff:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="このメールアドレスは既に使用されています"
            )

        # 確認トークン生成（32バイト = 64文字の16進数）
        verification_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        try:
            # リクエストレコード作成
            email_change_request = EmailChangeRequestModel(
                staff_id=staff_id,
                old_email=staff.email,  # 🐛 TDDで検出: old_emailフィールドを追加（NOT NULL制約対応）
                new_email=email_request.new_email,
                verification_token=verification_token,
                expires_at=expires_at,
                status="pending"
            )
            db.add(email_change_request)
            await db.flush()

            # スタッフ名を取得（フルネーム）
            staff_name = staff.full_name

            # 確認メール送信（新しいメールアドレス）
            try:
                await mail.send_email_change_verification(
                    new_email=email_request.new_email,
                    old_email=staff.email,
                    staff_name=staff_name,
                    verification_token=verification_token
                )
            except Exception as e:
                # メール送信失敗はログに記録するが、リクエストは成功とする
                print(f"確認メール送信失敗: {e}")

            # 通知メール送信（旧メールアドレス）
            try:
                await mail.send_email_change_notification(
                    old_email=staff.email,
                    staff_name=staff_name,
                    new_email=email_request.new_email
                )
            except Exception as e:
                print(f"通知メール送信失敗: {e}")

            await db.commit()

        except Exception as e:
            await db.rollback()
            raise

        return {
            "message": "確認メールを送信しました。新しいメールアドレスに届いたリンクをクリックして変更を完了してください。",
            "verification_token_expires_at": expires_at,
            "status": "pending"
        }

    async def verify_email_change(
        self,
        db: AsyncSession,
        verification_token: str
    ) -> Dict[str, any]:
        """
        メールアドレス変更を確認・完了

        手順:
        1. トークンでリクエストを検索
        2. 有効期限チェック
        3. ステータスチェック（既に使用済みでないか）
        4. スタッフ情報更新
        5. リクエストステータス更新
        6. 旧メールアドレスに完了通知送信
        7. 監査ログ記録
        """
        print(f"[DEBUG SERVICE] verify_email_change started with token: {verification_token[:10]}...")

        # トークンでリクエストを検索
        print(f"[DEBUG SERVICE] Searching for email change request with token...")
        stmt = (
            select(EmailChangeRequestModel)
            .where(EmailChangeRequestModel.verification_token == verification_token)
        )
        result = await db.execute(stmt)
        email_request = result.scalar_one_or_none()

        if not email_request:
            print(f"[DEBUG SERVICE] Email change request not found for token")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="無効な確認トークンです"
            )

        print(f"[DEBUG SERVICE] Found email change request: id={email_request.id}, status={email_request.status}")

        # 有効期限チェック
        print(f"[DEBUG SERVICE] Checking expiration: expires_at={email_request.expires_at}, now={datetime.now(timezone.utc)}")
        if datetime.now(timezone.utc) > email_request.expires_at:
            print(f"[DEBUG SERVICE] Token expired")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="確認トークンの有効期限が切れています"
            )

        # ステータスチェック
        print(f"[DEBUG SERVICE] Checking status: {email_request.status}")
        if email_request.status != "pending":
            print(f"[DEBUG SERVICE] Status is not pending")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="この変更リクエストは既に処理されています"
            )

        # スタッフ情報取得
        print(f"[DEBUG SERVICE] Fetching staff: staff_id={email_request.staff_id}")
        stmt_staff = select(Staff).where(Staff.id == email_request.staff_id)
        result_staff = await db.execute(stmt_staff)
        staff = result_staff.scalar_one_or_none()

        if not staff:
            print(f"[DEBUG SERVICE] Staff not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.STAFF_NOT_FOUND
            )

        print(f"[DEBUG SERVICE] Staff found: id={staff.id}, email={staff.email}")

        # 旧メールアドレスと新メールアドレスを保存（コミット後のアクセス用）
        old_email = staff.email
        new_email = email_request.new_email
        staff_name = staff.full_name
        print(f"[DEBUG SERVICE] Updating email from {old_email} to {new_email}")

        try:
            # スタッフ情報更新
            updated_at = datetime.now(timezone.utc)
            staff.email = new_email
            staff.updated_at = updated_at

            # リクエストステータス更新
            email_request.status = "completed"
            # verified_atは不要（updated_atで確認日時を判定）

            print(f"[DEBUG SERVICE] Flushing database changes...")
            await db.flush()

            # 監査ログ記録
            print(f"[DEBUG SERVICE] Creating audit log...")
            audit_log = AuditLog(
                staff_id=staff.id,
                action="UPDATE_EMAIL",
                old_value=old_email,
                new_value=new_email,
                timestamp=datetime.now(timezone.utc)
            )
            db.add(audit_log)
            await db.flush()

            # 旧メールアドレスに完了通知送信
            print(f"[DEBUG SERVICE] Sending completion email...")
            try:
                await mail.send_email_change_completed(
                    old_email=old_email,
                    staff_name=staff_name,
                    new_email=new_email
                )
            except Exception as e:
                print(f"完了通知メール送信失敗: {e}")

            print(f"[DEBUG SERVICE] Committing transaction...")
            await db.commit()

            # コミット後はモデル属性にアクセスできないため、保存した変数を使用
            result = {
                "message": "メールアドレスを変更しました",
                "new_email": new_email,
                "updated_at": updated_at
            }
            print(f"[DEBUG SERVICE] verify_email_change completed successfully: {result}")
            return result

        except Exception as e:
            await db.rollback()
            raise


staff_profile_service = StaffProfileService()
