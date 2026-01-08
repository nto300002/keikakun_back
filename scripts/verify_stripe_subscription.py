"""
Stripe サブスクリプション状態確認スクリプト

使用方法:
  python scripts/verify_stripe_subscription.py subscription <sub_id>
  python scripts/verify_stripe_subscription.py customer <cus_id>
"""
import stripe
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


def verify_subscription(subscription_id: str) -> dict:
    """
    サブスクリプションの状態を確認

    Args:
        subscription_id: Stripe Subscription ID

    Returns:
        サブスクリプション情報の辞書
    """
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)

        return {
            "id": subscription.id,
            "status": subscription.status,
            "customer": subscription.customer,
            "canceled_at": subscription.canceled_at,
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "cancel_at": subscription.cancel_at,
            "current_period_end": subscription.current_period_end,
            "current_period_start": subscription.current_period_start,
            "items": [
                {
                    "price_id": item.price.id,
                    "quantity": item.quantity
                }
                for item in subscription["items"]["data"]
            ]
        }

    except stripe.error.InvalidRequestError as e:
        if "No such subscription" in str(e):
            return {
                "error": "Subscription not found",
                "subscription_id": subscription_id,
                "note": "This may indicate the subscription was permanently deleted."
            }
        raise


def verify_customer_subscriptions(customer_id: str) -> list:
    """
    カスタマーの全サブスクリプションを確認

    Args:
        customer_id: Stripe Customer ID

    Returns:
        サブスクリプションリスト
    """
    try:
        subscriptions = stripe.Subscription.list(
            customer=customer_id,
            limit=100
        )

        return [
            {
                "id": sub.id,
                "status": sub.status,
                "canceled_at": sub.canceled_at,
                "cancel_at": sub.cancel_at,
                "current_period_end": sub.current_period_end
            }
            for sub in subscriptions.data
        ]

    except stripe.error.InvalidRequestError as e:
        if "No such customer" in str(e):
            return {
                "error": "Customer not found",
                "customer_id": customer_id
            }
        raise


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python scripts/verify_stripe_subscription.py subscription <sub_id>")
        print("  python scripts/verify_stripe_subscription.py customer <cus_id>")
        print("\nExamples:")
        print("  python scripts/verify_stripe_subscription.py subscription sub_1AbCdEfGhIjKlMnO")
        print("  python scripts/verify_stripe_subscription.py customer cus_1AbCdEfGhIjKlMnO")
        sys.exit(1)

    command = sys.argv[1]
    id_value = sys.argv[2]

    if command == "subscription":
        result = verify_subscription(id_value)
        print("\n" + "="*60)
        print("Subscription Info:")
        print("="*60)
        for key, value in result.items():
            print(f"  {key}: {value}")
        print("="*60 + "\n")

    elif command == "customer":
        result = verify_customer_subscriptions(id_value)
        if isinstance(result, dict) and "error" in result:
            print(f"\nError: {result['error']}")
            print(f"Customer ID: {result['customer_id']}\n")
        else:
            print("\n" + "="*60)
            print(f"Customer Subscriptions ({len(result)} found):")
            print("="*60)
            for i, sub in enumerate(result, 1):
                print(f"\n{i}. Subscription {sub['id']}:")
                for key, value in sub.items():
                    if key != 'id':
                        print(f"     {key}: {value}")
            print("="*60 + "\n")

    else:
        print(f"Unknown command: {command}")
        print("Use 'subscription' or 'customer'")
        sys.exit(1)
