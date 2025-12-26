"""
Billing API エンドポイント (Phase 2)
"""
from typing import Annotated
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
import stripe
import logging

from app import crud
from app.api import deps
from app.models.staff import Staff
from app.models.enums import BillingStatus
from app.schemas.billing import BillingStatusResponse
from app.core.config import settings
from app.messages import ja
from app.services import BillingService


def get_stripe_secret_key() -> str:
    """
    STRIPE_SECRET_KEYの値を安全に取得

    SecretStr型と通常のstr型の両方に対応
    テスト環境ではstr型でモックされることがあるため
    """
    key = settings.STRIPE_SECRET_KEY
    if isinstance(key, str):
        return key
    elif key:  # SecretStrの場合
        return key.get_secret_value()
    raise ValueError("STRIPE_SECRET_KEY is not configured")


# Stripe APIキーの設定
if settings.STRIPE_SECRET_KEY:
    stripe.api_key = get_stripe_secret_key()

router = APIRouter()
logger = logging.getLogger(__name__)

# サービス層のインスタンス化
billing_service = BillingService()


@router.get("/status", response_model=BillingStatusResponse)
async def get_billing_status(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[Staff, Depends(deps.get_current_user)]
) -> BillingStatusResponse:
    """
    課金ステータス取得API

    認証済みユーザーのみアクセス可能
    現在のStaffが所属するOfficeのBilling情報を返す
    レスポンスタイム: 500ms以内
    """
    # 現在のユーザーが所属する事務所を取得
    if not current_user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.BILLING_OFFICE_NOT_FOUND
        )

    # プライマリの事務所を取得
    primary_association = next(
        (assoc for assoc in current_user.office_associations if assoc.is_primary),
        current_user.office_associations[0]  # プライマリがない場合は最初の事務所
    )
    office_id = primary_association.office_id

    # Billing情報を取得
    billing = await crud.billing.get_by_office_id(db=db, office_id=office_id)

    # Billing情報が存在しない場合、自動的に作成（既存Officeの救済措置）
    if not billing:
        logger.warning(f"Billing not found for office {office_id}, auto-creating with 180-day trial")
        billing = await crud.billing.create_for_office(
            db=db,
            office_id=office_id,
            trial_days=180
        )
        logger.info(f"Auto-created billing record: id={billing.id}, office_id={office_id}")

    return BillingStatusResponse(
        billing_status=billing.billing_status,
        trial_end_date=billing.trial_end_date,
        next_billing_date=billing.next_billing_date,
        current_plan_amount=billing.current_plan_amount,
        subscription_start_date=billing.subscription_start_date,
        scheduled_cancel_at=billing.scheduled_cancel_at
    )


@router.post("/create-checkout-session")
async def create_checkout_session(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[Staff, Depends(deps.require_owner)]
):
    """
    Stripe Checkout Session作成API（サービス層利用版）

    オーナー権限のみ実行可能
    MissingGreenletエラーを解決し、トランザクション整合性を保証

    改善点:
    - サービス層でトランザクション管理を一元化
    - Stripe API呼び出しとDB操作の順序を最適化
    - MissingGreenletエラーの根本的な解決
    """
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PRICE_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ja.BILLING_STRIPE_NOT_CONFIGURED
        )

    # 現在のユーザーが所属する事務所を取得
    if not current_user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.BILLING_OFFICE_NOT_FOUND
        )

    primary_association = next(
        (assoc for assoc in current_user.office_associations if assoc.is_primary),
        current_user.office_associations[0]
    )
    office_id = primary_association.office_id

    # Billing情報を取得
    billing = await crud.billing.get_by_office_id(db=db, office_id=office_id)
    if not billing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.BILLING_INFO_NOT_FOUND
        )

    # Office情報を取得
    office = await crud.office.get(db=db, id=office_id)
    if not office:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_INFO_NOT_FOUND
        )

    # 既にCustomer IDがある場合
    if billing.stripe_customer_id:
        # 既存のCustomerでCheckout Sessionを作成
        try:
            checkout_session = stripe.checkout.Session.create(
                mode='subscription',
                customer=billing.stripe_customer_id,
                line_items=[{
                    'price': settings.STRIPE_PRICE_ID,
                    'quantity': 1
                }],
                subscription_data={
                    'trial_end': int(billing.trial_end_date.timestamp()),
                    'metadata': {
                        'office_id': str(office_id),
                        'office_name': office.name,
                        'created_by_user_id': str(current_user.id),
                    }
                },
                automatic_tax={'enabled': True},
                customer_update={'address': 'auto'},
                billing_address_collection='required',
                payment_method_types=['card'],
                success_url=f"{settings.FRONTEND_URL}/admin?tab=plan&success=true",
                cancel_url=f"{settings.FRONTEND_URL}/admin?tab=plan&canceled=true",
            )

            return {
                "session_id": checkout_session.id,
                "url": checkout_session.url
            }

        except Exception as e:
            logger.error(f"Stripe Checkout Session作成エラー: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ja.BILLING_CHECKOUT_SESSION_FAILED
            )

    # Customer IDがない場合: サービス層で作成
    return await billing_service.create_checkout_session_with_customer(
        db=db,
        billing_id=billing.id,
        office_id=office_id,
        office_name=office.name,
        user_email=current_user.email,
        user_id=current_user.id,
        trial_end_date=billing.trial_end_date,
        stripe_secret_key=get_stripe_secret_key(),
        stripe_price_id=settings.STRIPE_PRICE_ID,
        frontend_url=settings.FRONTEND_URL
    )


@router.post("/create-portal-session")
async def create_portal_session(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[Staff, Depends(deps.require_owner)]
):
    """
    Stripe Customer Portal Session作成API

    オーナー権限のみ実行可能
    サブスク管理画面（キャンセル・カード変更）へのリンクを返す
    """
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ja.BILLING_STRIPE_NOT_CONFIGURED
        )

    # 現在のユーザーが所属する事務所を取得
    if not current_user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.BILLING_OFFICE_NOT_FOUND
        )

    primary_association = next(
        (assoc for assoc in current_user.office_associations if assoc.is_primary),
        current_user.office_associations[0]
    )
    office_id = primary_association.office_id

    # Billing情報を取得
    billing = await crud.billing.get_by_office_id(db=db, office_id=office_id)
    if not billing or not billing.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.BILLING_STRIPE_CUSTOMER_NOT_FOUND
        )

    # Customer Portal Sessionを作成
    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=billing.stripe_customer_id,
            return_url=f"{settings.FRONTEND_URL}/admin/plan",
        )

        return {"url": portal_session.url}

    except Exception as e:
        logger.error(f"Stripe Customer Portal Session作成エラー: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.BILLING_PORTAL_SESSION_FAILED
        )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    stripe_signature: Annotated[str, Header(alias="Stripe-Signature")]
):
    """
    Stripe Webhook受信API（サービス層利用版）

    処理対象イベント:
    - customer.subscription.created: billing_status → early_payment or active
    - customer.subscription.updated: cancel_at_period_end=true時 → canceling
    - invoice.payment_succeeded: billing_status → active
    - invoice.payment_failed: billing_status → past_due
    - customer.subscription.deleted: billing_status → canceled

    改善点:
    - サービス層でトランザクション管理を一元化
    - 全ての操作を1つのトランザクションで実行
    - データ整合性を保証
    - Stripe署名検証必須
    - 冪等性を保証
    - 監査ログに記録
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ja.BILLING_WEBHOOK_SECRET_NOT_SET
        )

    # リクエストボディを取得
    payload = await request.body()

    # Stripe署名を検証
    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_signature,
            settings.STRIPE_WEBHOOK_SECRET.get_secret_value()
        )
    except ValueError:
        logger.error("Invalid payload")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ja.BILLING_WEBHOOK_INVALID_PAYLOAD)
    except stripe.error.SignatureVerificationError:
        logger.error("Invalid signature")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ja.BILLING_WEBHOOK_INVALID_SIGNATURE)

    # イベントタイプによって処理を分岐
    event_type = event['type']
    event_data = event['data']['object']
    event_id = event.get('id', 'unknown')

    # 【Phase 7】冪等性チェック: 既に処理済みのイベントはスキップ
    is_processed = await crud.webhook_event.is_event_processed(db=db, event_id=event_id)
    if is_processed:
        logger.info(f"[Webhook:{event_id}] Event already processed - skipping")
        return {"status": "success", "message": "Event already processed"}

    # サービス層で処理（トランザクション整合性保証）
    try:
        if event_type == 'invoice.payment_succeeded':
            # 支払い成功 → active
            customer_id = event_data.get('customer')
            await billing_service.process_payment_succeeded(
                db=db,
                event_id=event_id,
                customer_id=customer_id
            )

        elif event_type == 'invoice.payment_failed':
            # 支払い失敗 → past_due
            customer_id = event_data.get('customer')
            await billing_service.process_payment_failed(
                db=db,
                event_id=event_id,
                customer_id=customer_id
            )

        elif event_type == 'customer.subscription.created':
            # サブスク作成 → early_payment or active
            await billing_service.process_subscription_created(
                db=db,
                event_id=event_id,
                subscription_data=event_data
            )

        elif event_type == 'customer.subscription.updated':
            # サブスク更新（キャンセル予定など） → canceling
            await billing_service.process_subscription_updated(
                db=db,
                event_id=event_id,
                subscription_data=event_data
            )

        elif event_type == 'customer.subscription.deleted':
            # サブスクキャンセル → canceled
            customer_id = event_data.get('customer')
            await billing_service.process_subscription_deleted(
                db=db,
                event_id=event_id,
                customer_id=customer_id
            )

        else:
            # 未対応のイベントタイプ
            logger.info(f"[Webhook:{event_id}] Unhandled event type: {event_type}")

        return {"status": "success"}

    except Exception as e:
        # エラーはサービス層で既にロールバック済み
        logger.error(f"[Webhook:{event_id}] Webhook処理エラー: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.BILLING_WEBHOOK_PROCESSING_FAILED
        )
