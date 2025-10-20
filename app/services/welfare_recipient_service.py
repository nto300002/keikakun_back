"""
Welfare Recipient Service

このサービスは利用者登録に関するビジネスロジックを管理します。
mini.mdの要件に基づいて、利用者情報と初期支援計画の一括作成を行います。
"""

from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
import uuid

from app.crud.crud_welfare_recipient import crud_welfare_recipient
from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.enums import SupportPlanStep
from app.schemas.welfare_recipient import UserRegistrationRequest
from app.core.exceptions import BadRequestException, InternalServerException
from datetime import timedelta
import logging
import inspect
import asyncio

logger = logging.getLogger(__name__)

class WelfareRecipientService:
    """
    利用者登録サービス

    mini.mdの要件に基づいて以下の処理を行います：
    1. 利用者基本情報の作成
    2. 詳細情報（住所、緊急連絡先等）の作成
    3. 障害情報の作成
    4. 初期支援計画サイクルと全ステップステータスの一括作成
    5. 事業所との関連付け

    全ての処理は単一トランザクション内で実行され、
    エラー発生時は自動的にロールバックされます。
    """

    @staticmethod
    async def create_recipient_with_initial_plan(
        db: AsyncSession,
        registration_data: UserRegistrationRequest,
        office_id: UUID
    ) -> WelfareRecipient:
        """
        利用者情報と初期支援計画の一括作成 (非同期)
        """
        try:
            logger.info("[SERVICE DEBUG] create_recipient_with_initial_plan START")
            # Pydanticによる型変換とバリデーションが完了しているため、手動バリデーションは不要

            # 2. 利用者基本情報の作成
            basic_info = registration_data.basic_info
            logger.info(f"[SERVICE DEBUG] Creating WelfareRecipient: {basic_info.lastName} {basic_info.firstName}")
            welfare_recipient = WelfareRecipient(
                first_name=basic_info.firstName,
                last_name=basic_info.lastName,
                first_name_furigana=basic_info.firstNameFurigana,
                last_name_furigana=basic_info.lastNameFurigana,
                birth_day=basic_info.birthDay,
                gender=basic_info.gender
            )
            db.add(welfare_recipient)
            logger.info("[SERVICE DEBUG] Flushing WelfareRecipient...")
            await db.flush()  # IDを取得するためにflush

            # IMPORTANT: flush()直後にIDを変数に保存する
            # その後の処理（flush等）でオブジェクトがexpired状態になり、
            # 再度welfare_recipient.idにアクセスするとgreenletエラーが発生するため
            recipient_id = welfare_recipient.id
            logger.info(f"[SERVICE DEBUG] WelfareRecipient created with id={recipient_id}")

            # 3. 関連データの作成
            logger.info("[SERVICE DEBUG] Calling crud_welfare_recipient.create_related_data...")
            await crud_welfare_recipient.create_related_data(
                db=db,
                welfare_recipient=welfare_recipient,
                registration_data=registration_data,
                office_id=office_id
            )
            logger.info("[SERVICE DEBUG] create_related_data completed")

            # 4. 初期支援計画の作成（mini.mdの要件）
            # 既に保存したrecipient_idを使用（welfare_recipient.idに再アクセスしない）
            logger.info("[SERVICE DEBUG] Calling _create_initial_support_plan...")
            await WelfareRecipientService._create_initial_support_plan(db, recipient_id, office_id)
            logger.info("[SERVICE DEBUG] _create_initial_support_plan completed")

            # 5. IDを返す (コミット/ロールバックは呼び出し元で行う)
            logger.info(f"[SERVICE DEBUG] create_recipient_with_initial_plan END: returning recipient_id={recipient_id}")
            return recipient_id

        except IntegrityError as e:
            logger.error(f"[SERVICE DEBUG] IntegrityError occurred: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[SERVICE DEBUG] Traceback:\n{traceback.format_exc()}")
            # トランザクション管理は呼び出し元（エンドポイント層）で行うため、ここではrollbackしない
            raise BadRequestException("データの整合性エラーが発生しました。")

        except SQLAlchemyError as e:
            logger.error(f"[SERVICE DEBUG] SQLAlchemyError occurred: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[SERVICE DEBUG] Traceback:\n{traceback.format_exc()}")
            # トランザクション管理は呼び出し元（エンドポイント層）で行うため、ここではrollbackしない
            raise InternalServerException(f"データベースエラーが発生しました: {e}")

        except Exception as e:
            logger.error(f"[SERVICE DEBUG] Unexpected exception occurred: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[SERVICE DEBUG] Traceback:\n{traceback.format_exc()}")
            # トランザクション管理は呼び出し元（エンドポイント層）で行うため、ここではrollbackしない
            raise

    @staticmethod
    def _validate_registration_data(registration_data: UserRegistrationRequest) -> None:
        """
        登録データのバリデーション (Pydanticに移行したため、現在は未使用)
        """
        # Pydanticスキーマでほとんどのバリデーションが行われるようになったため、
        # この手動バリデーションは不要になります。
        # カスタムのクロスフィールドバリデーションが必要な場合のみ残します。
        pass

    @staticmethod
    async def _create_initial_support_plan(db: AsyncSession, welfare_recipient_id: UUID, office_id: UUID) -> None:
        """
        利用者作成時の初期支援計画 (サイクル + ステータス) を作成する (非同期)。
        サイクル番号に応じて作成するステップを変更する。
        カレンダーイベントも自動作成する。
        """
        logger.info(f"[DEBUG] _create_initial_support_plan START: welfare_recipient_id={welfare_recipient_id}, office_id={office_id}")

        # 既存のサイクル数を取得して新しいサイクル番号を決定
        logger.info("[DEBUG] Counting existing cycles...")
        count_stmt = select(func.count()).select_from(SupportPlanCycle).where(SupportPlanCycle.welfare_recipient_id == welfare_recipient_id)
        existing_cycles_count = (await db.execute(count_stmt)).scalar_one()
        new_cycle_number = existing_cycles_count + 1
        logger.info(f"[DEBUG] New cycle_number={new_cycle_number}")

        logger.info("[DEBUG] Creating SupportPlanCycle...")
        cycle = SupportPlanCycle(
            welfare_recipient_id=welfare_recipient_id,
            office_id=office_id,
            is_latest_cycle=True,
            cycle_number=new_cycle_number,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=date.today() + timedelta(days=180)
        )
        db.add(cycle)
        logger.info("[DEBUG] Flushing cycle...")
        await db.flush()  # cycle.id を取得するため
        logger.info(f"[DEBUG] Cycle created with id={cycle.id}")

        if new_cycle_number == 1:
            initial_steps = [
                SupportPlanStep.assessment,
                SupportPlanStep.draft_plan,
                SupportPlanStep.staff_meeting,
                SupportPlanStep.final_plan_signed
            ]
        else:
            initial_steps = [
                SupportPlanStep.monitoring,
                SupportPlanStep.draft_plan,
                SupportPlanStep.staff_meeting,
                SupportPlanStep.final_plan_signed
            ]

        logger.info(f"[DEBUG] Creating {len(initial_steps)} status records...")
        for i, step in enumerate(initial_steps):
            status = SupportPlanStatus(
                plan_cycle_id=cycle.id,
                welfare_recipient_id=welfare_recipient_id,
                office_id=office_id,
                step_type=step,
                completed=False,
                is_latest_status=(i == 0)  # 最初のステップを最新にする
            )
            db.add(status)

        logger.info("[DEBUG] Flushing status records...")
        await db.flush()
        logger.info("[DEBUG] Status records created successfully")

        # カレンダーイベントを自動作成（ベストエフォート：失敗してもサイクル作成は継続）
        logger.info("[DEBUG] Creating calendar events...")
        try:
            from app.services.calendar_service import calendar_service
            from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError

            # 更新期限イベント（150日目～180日目の1イベント）
            try:
                await calendar_service.create_renewal_deadline_events(
                    db=db,
                    office_id=office_id,
                    welfare_recipient_id=welfare_recipient_id,
                    cycle_id=cycle.id,
                    next_renewal_deadline=cycle.next_renewal_deadline
                )
                logger.info("[DEBUG] Renewal deadline event created successfully")
            except SQLAlchemyIntegrityError as e:
                # 重複エラーの場合は警告のみ（既にイベントが存在する）
                logger.warning(f"[DEBUG] Renewal deadline event already exists for cycle_id={cycle.id}: {e}")
            except Exception as e:
                # その他のエラーも警告のみ（カレンダー設定がない等）
                logger.warning(f"[DEBUG] Could not create renewal deadline events: {type(e).__name__}: {e}")

            # モニタリング期限イベント（cycle_number>=2の場合のみ、1~7日の7イベント）
            try:
                await calendar_service.create_monitoring_deadline_events(
                    db=db,
                    office_id=office_id,
                    welfare_recipient_id=welfare_recipient_id,
                    cycle_id=cycle.id,
                    cycle_start_date=cycle.plan_cycle_start_date,
                    cycle_number=new_cycle_number
                )
                logger.info("[DEBUG] Monitoring deadline events created successfully")
            except SQLAlchemyIntegrityError as e:
                # 重複エラーの場合は警告のみ（既にイベントが存在する）
                logger.warning(f"[DEBUG] Monitoring deadline events already exist for cycle_id={cycle.id}: {e}")
            except Exception as e:
                # その他のエラーも警告のみ（cycle_number=1等）
                logger.warning(f"[DEBUG] Could not create monitoring deadline events: {type(e).__name__}: {e}")

        except Exception as e:
            # calendar_service自体のインポートエラー等、予期しないエラー
            logger.error(f"[DEBUG] Unexpected error during calendar event creation: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
            # カレンダーイベント作成の失敗は利用者登録を妨げない

        logger.info("[DEBUG] _create_initial_support_plan END")

    @staticmethod
    def _create_initial_support_plan_sync(db: Session, welfare_recipient_id: UUID) -> None:
        """
        利用者作成時の初期支援計画 (サイクル + ステータス) を作成する (同期版)。
        """
        # 既存のサイクル数を取得して新しいサイクル番号を決定
        count_stmt = select(func.count()).select_from(SupportPlanCycle).where(SupportPlanCycle.welfare_recipient_id == welfare_recipient_id)
        existing_cycles_count = db.execute(count_stmt).scalar_one()
        new_cycle_number = existing_cycles_count + 1

        cycle = SupportPlanCycle(
            welfare_recipient_id=welfare_recipient_id,
            is_latest_cycle=True,
            cycle_number=new_cycle_number,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=date.today() + timedelta(days=180)
        )
        db.add(cycle)
        db.flush()  # cycle.id を取得するため

        if new_cycle_number == 1:
            initial_steps = [
                SupportPlanStep.assessment,
                SupportPlanStep.draft_plan,
                SupportPlanStep.staff_meeting,
                SupportPlanStep.final_plan_signed
            ]
        else:
            initial_steps = [
                SupportPlanStep.monitoring,
                SupportPlanStep.draft_plan,
                SupportPlanStep.staff_meeting,
                SupportPlanStep.final_plan_signed
            ]

        for i, step in enumerate(initial_steps):
            status = SupportPlanStatus(
                plan_cycle_id=cycle.id,
                step_type=step,
                completed=False,
                is_latest_status=(i == 0)  # 最初のステップを最新にする
            )
            db.add(status)

        db.flush()

    # ... (check_data_integrity, repair_support_plan_data, _repair_missing_statuses は同期のまま)
    @staticmethod
    def check_data_integrity(db: Session, welfare_recipient_id: UUID) -> dict:
        """
        利用者データの整合性チェック

        mini.mdで定義された修復機能のための検証ロジック

        Args:
            db: データベースセッション
            welfare_recipient_id: 利用者ID

        Returns:
            整合性チェック結果
        """
        result = {
            "is_valid": True,
            "missing_components": [],
            "issues": []
        }

        try:
            # 利用者情報の存在確認
            welfare_recipient = crud_welfare_recipient.get(db, welfare_recipient_id)
            if not welfare_recipient:
                result["is_valid"] = False
                result["issues"].append("利用者情報が見つかりません")
                return result

            # 支援計画サイクルの存在確認
            from sqlalchemy import select
            cycle_stmt = select(SupportPlanCycle).where(
                SupportPlanCycle.welfare_recipient_id == welfare_recipient_id,
                SupportPlanCycle.is_latest_cycle == True
            )
            latest_cycle = db.execute(cycle_stmt).scalars().first()

            if not latest_cycle:
                result["is_valid"] = False
                result["missing_components"].append("支援計画サイクル")
            else:
                # ステータスの存在確認
                status_stmt = select(SupportPlanStatus).where(
                    SupportPlanStatus.support_plan_cycle_id == latest_cycle.id
                )
                statuses = list(db.execute(status_stmt).scalars().all())

                if latest_cycle.cycle_number == 1:
                    expected_steps = [
                        SupportPlanStep.assessment,
                        SupportPlanStep.draft_plan,
                        SupportPlanStep.staff_meeting,
                        SupportPlanStep.final_plan_signed
                    ]
                else:
                    expected_steps = [
                        SupportPlanStep.monitoring,
                        SupportPlanStep.draft_plan,
                        SupportPlanStep.staff_meeting,
                        SupportPlanStep.final_plan_signed
                    ]

                existing_steps = [status.step for status in statuses]
                missing_steps = [step for step in expected_steps if step not in existing_steps]

                if missing_steps:
                    result["is_valid"] = False
                    result["missing_components"].extend([f"ステップ_{step.value}" for step in missing_steps])

            return result

        except Exception as e:
            print(f"Error checking data integrity: {str(e)}")
            result["is_valid"] = False
            result["issues"].append(f"整合性チェック中にエラーが発生しました: {str(e)}")
            return result

    @staticmethod
    def repair_support_plan_data(db: Session, welfare_recipient_id: UUID) -> bool:
        """
        支援計画データの修復


        Args:
            db: データベースセッション
            welfare_recipient_id: 利用者ID

        Returns:
            修復成功フラグ
        """
        try:
            print(f"Starting support plan repair for recipient {welfare_recipient_id}")

            # 整合性チェック
            integrity_result = WelfareRecipientService.check_data_integrity(db, welfare_recipient_id)

            if integrity_result["is_valid"]:
                print("No repair needed - data is already consistent")
                return True

            # 修復処理
            if "支援計画サイクル" in integrity_result["missing_components"]:
                # サイクル自体が存在しない場合は新規作成
                WelfareRecipientService._create_initial_support_plan_sync(db, welfare_recipient_id)
            else:
                # ステータスのみ不足している場合は部分修復
                WelfareRecipientService._repair_missing_statuses(db, welfare_recipient_id)

            db.commit()
            print(f"Successfully repaired support plan for recipient {welfare_recipient_id}")
            return True

        except Exception as e:
            print(f"Error during support plan repair: {str(e)}")
            db.rollback()
            return False

    @staticmethod
    def _repair_missing_statuses(db: Session, welfare_recipient_id: UUID) -> None:
        """
        不足しているステータスの修復

        Args:
            db: データベースセッション
            welfare_recipient_id: 利用者ID
        """
        from sqlalchemy import select

        # 最新サイクルを取得
        cycle_stmt = select(SupportPlanCycle).where(
            SupportPlanCycle.welfare_recipient_id == welfare_recipient_id,
            SupportPlanCycle.is_latest_cycle == True
        )
        latest_cycle = db.execute(cycle_stmt).scalars().first()

        if not latest_cycle:
            raise Exception("最新の支援計画サイクルが見つかりません")

        # 既存のステータスを確認
        status_stmt = select(SupportPlanStatus).where(
            SupportPlanStatus.support_plan_cycle_id == latest_cycle.id
        )
        existing_statuses = list(db.execute(status_stmt).scalars().all())
        existing_steps = [status.step for status in existing_statuses]

        # 必要なステップを特定
        if latest_cycle.cycle_number == 1:
            required_steps = [
                SupportPlanStep.assessment,
                SupportPlanStep.draft_plan,
                SupportPlanStep.staff_meeting,
                SupportPlanStep.final_plan_signed
            ]
        else:
            required_steps = [
                SupportPlanStep.monitoring,
                SupportPlanStep.draft_plan,
                SupportPlanStep.staff_meeting,
                SupportPlanStep.final_plan_signed
            ]

        # 不足しているステップを追加
        for step in required_steps:
            if step not in existing_steps:
                status = SupportPlanStatus(
                    support_plan_cycle_id=latest_cycle.id,
                    step=step,
                    completed=False,
                    completed_at=None
                )
                db.add(status)
                print(f"Added missing status: {step.value}")

    @staticmethod
    async def create_recipient_with_details(db: AsyncSession, registration_data: UserRegistrationRequest, office_id: UUID, **kwargs):
        """非同期の作成メソッドを呼び出すラッパー"""
        return await WelfareRecipientService.create_recipient_with_initial_plan(
            db=db,
            registration_data=registration_data,
            office_id=office_id,
            **kwargs
        )

    def check_and_repair_plan_data(self, db, welfare_recipient_id):
        """
        同期呼び出し向け互換メソッド。
        - 存在しない場合は初期サイクルを作成する
        - サイクルはあるがステータスが不足している場合は補完する
        戻り値: (repaired: bool, message: str)
        """
        from sqlalchemy import select

        try:
            cycle_stmt = select(SupportPlanCycle).where(
                SupportPlanCycle.welfare_recipient_id == welfare_recipient_id,
                SupportPlanCycle.is_latest_cycle == True
            )
            latest_cycle = db.execute(cycle_stmt).scalars().first()

            if not latest_cycle:
                # 初期サイクルが無ければ作成
                self._create_initial_support_plan_sync(db, welfare_recipient_id)
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                return True, "初期支援計画サイクルとステータスを作成しました"

            # サイクルは存在 -> 不足ステータスを修復
            try:
                self._repair_missing_statuses(db, welfare_recipient_id)
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                return True, "不足しているステータスを確認・修復しました"
            except Exception as e:
                try:
                    db.rollback()
                except Exception:
                    pass
                return False, f"修復中にエラー: {e}"

        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            return False, f"チェック実行中にエラー: {e}"

    async def repair_recipient_support_plan(self, db: AsyncSession, welfare_recipient_id: uuid.UUID, performed_by: uuid.UUID | None = None) -> tuple[bool, str]:
        """
        利用者の支援計画データを点検・修復する (async)。
        戻り値: (repaired: bool, message: str)
        """
        try:
            # 利用者の office_id を取得
            from app.models.welfare_recipient import OfficeWelfareRecipient
            office_stmt = select(OfficeWelfareRecipient.office_id).where(
                OfficeWelfareRecipient.welfare_recipient_id == welfare_recipient_id
            ).limit(1)
            office_result = await db.execute(office_stmt)
            office_id = office_result.scalar_one_or_none()

            if not office_id:
                return False, "利用者の事業所情報が見つかりません"

            # 最新サイクルを取得
            stmt = select(SupportPlanCycle).where(
                SupportPlanCycle.welfare_recipient_id == welfare_recipient_id,
                SupportPlanCycle.is_latest_cycle == True
            ).options(selectinload(SupportPlanCycle.statuses)) # Eager load statuses
            res = await db.execute(stmt)
            latest_cycle = res.scalars().first()

            if not latest_cycle:
                # 初期サイクルと初期ステータスを作成
                cycle = SupportPlanCycle(
                    welfare_recipient_id=welfare_recipient_id,
                    office_id=office_id,
                    is_latest_cycle=True,
                    plan_cycle_start_date=date.today(),
                    next_renewal_deadline=date.today()
                )
                db.add(cycle)
                await db.flush()

                initial_steps = [
                    SupportPlanStep.assessment,
                    SupportPlanStep.draft_plan,
                    SupportPlanStep.staff_meeting,
                ]

                for step in initial_steps:
                    st = SupportPlanStatus(
                        plan_cycle_id=cycle.id,
                        welfare_recipient_id=welfare_recipient_id,
                        office_id=office_id,
                        step_type=step,
                        completed=False
                    )
                    db.add(st)
                await db.flush()
                await db.commit()
                return True, "初期支援計画サイクルとステータスを作成しました"

            # 既存サイクル -> 不足ステータス補完
            created = await self._repair_missing_statuses_async(db, welfare_recipient_id, latest_cycle)
            if created > 0:
                await db.commit()
                return True, f"不足していた {created} 件のステータスを作成しました"

            return False, "データは正常です"

        except Exception as e:
            try:
                await db.rollback()
            except Exception:
                pass
            return False, f"修復中にエラー: {e}"

    async def _repair_missing_statuses_async(self, db: AsyncSession, welfare_recipient_id: uuid.UUID, latest_cycle: SupportPlanCycle) -> int:
        """
        最新サイクルの不足ステータスを補完する (async)。
        返却: 追加したステータス数
        """
        if not latest_cycle:
            raise Exception("最新サイクルが見つかりません")

        # 要件に合わせるべき初期ステータス定義
        required_steps = [
            SupportPlanStep.assessment,
            SupportPlanStep.draft_plan,
            SupportPlanStep.staff_meeting,
        ]

        # 既存ステップを取得
        # latest_cycle.statuses を直接使うことで、遅延読み込みをトリガーする
        existing_steps = [s.step_type for s in latest_cycle.statuses]

        to_create = [step for step in required_steps if step not in existing_steps]
        for step in to_create:
            st = SupportPlanStatus(
                plan_cycle_id=latest_cycle.id,
                welfare_recipient_id=latest_cycle.welfare_recipient_id,
                office_id=latest_cycle.office_id,
                step_type=step,
                completed=False
            )
            db.add(st)

        if to_create:
            await db.flush()
        return len(to_create)

    async def delete_recipient(
        self,
        db: AsyncSession,
        recipient_id: UUID
    ) -> bool:
        """利用者を削除（関連カレンダーイベントもGoogle Calendarから削除）

        【責務の説明】
        利用者削除には2つのアプローチがあります：
        1. crud層の `delete_with_cascade`: データベースのみの削除（CASCADE削除を含む）
        2. services層の `delete_recipient`（このメソッド）: ビジネスロジックを含む削除

        このメソッドを使うべき理由：
        - Google Calendar APIを呼び出してクラウド側からもイベントを削除する
        - データベースのCASCADEだけでは、Google Calendar上のイベントは削除されない
        - カレンダーイベントの完全な削除（DB + Google Calendar）を保証する

        Args:
            db: データベースセッション
            recipient_id: 利用者ID

        Returns:
            削除成功フラグ
        """
        logger.info(f"[DEBUG] delete_recipient START: recipient_id={recipient_id}")

        # 1. 利用者に紐づくカレンダーイベントを取得
        from app.models.calendar_events import CalendarEvent
        from app.crud.crud_office_calendar_account import crud_office_calendar_account

        stmt = select(CalendarEvent).where(
            CalendarEvent.welfare_recipient_id == recipient_id
        )
        result = await db.execute(stmt)
        events = result.scalars().all()

        logger.info(f"[DEBUG] Found {len(events)} calendar events for recipient {recipient_id}")

        # 2. Google Calendarから各イベントを削除
        for event in events:
            # MissingGreenletエラーを防ぐため、必要な属性を事前に変数に保存
            event_id = event.id
            google_event_id = event.google_event_id
            office_id = event.office_id

            if google_event_id:
                try:
                    logger.info(f"[DEBUG-DELETE] Processing event {event_id} with google_event_id={google_event_id}, office_id={office_id}")

                    # カレンダーアカウント取得
                    account = await crud_office_calendar_account.get_by_office_id(
                        db=db,
                        office_id=office_id
                    )
                    logger.info(f"[DEBUG-DELETE] Calendar account retrieved: {account is not None}")

                    if account:
                        logger.info(f"[DEBUG-DELETE] Account attributes: service_account_key exists={hasattr(account, 'service_account_key')}, decrypt method exists={hasattr(account, 'decrypt_service_account_key')}")

                        # Google Calendarクライアント初期化
                        from app.services.google_calendar_client import GoogleCalendarClient

                        # decrypt_service_account_key() はメソッドなので呼び出す必要がある
                        decrypted_key = account.decrypt_service_account_key()
                        logger.info(f"[DEBUG-DELETE] Decrypted key obtained: {decrypted_key is not None}")

                        calendar_client = GoogleCalendarClient(
                            service_account_json=decrypted_key,
                            calendar_id=account.google_calendar_id
                        )
                        logger.info(f"[DEBUG-DELETE] GoogleCalendarClient initialized")

                        # Google Calendarからイベント削除
                        await calendar_client.delete_event(google_event_id)
                        logger.info(f"[DEBUG] Deleted event {event_id} from Google Calendar: {google_event_id}")
                    else:
                        logger.warning(f"[DEBUG] Calendar account not found for office_id={office_id}")

                except Exception as e:
                    # Google Calendar削除に失敗してもDB削除は継続
                    logger.warning(f"[DEBUG] Failed to delete event {event_id} from Google Calendar: {str(e)}")
                    import traceback
                    logger.warning(f"[DEBUG-DELETE] Traceback:\n{traceback.format_exc()}")

        # 3. 利用者削除（CASCADE でイベントも削除される）
        recipient = await db.get(WelfareRecipient, recipient_id)
        if recipient:
            await db.delete(recipient)
            await db.flush()
            logger.info(f"[DEBUG] delete_recipient END: deleted recipient {recipient_id}")
            return True

        logger.warning(f"[DEBUG] delete_recipient END: recipient {recipient_id} not found")
        return False

# ensure module exports an instance expected by tests/endpoints
try:
    welfare_recipient_service  # type: ignore[name-defined]
except NameError:
    welfare_recipient_service = WelfareRecipientService()

__all__ = globals().get("__all__", []) + ["WelfareRecipientService", "welfare_recipient_service"]
