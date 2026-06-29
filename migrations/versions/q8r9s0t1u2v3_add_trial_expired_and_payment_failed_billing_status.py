"""Add trial_expired and payment_failed billing statuses

Revision ID: q8r9s0t1u2v3
Revises: p7q8r9s0t1u2
Create Date: 2026-06-18

BillingStatus enumに以下を追加する。
- trial_expired: trial終了後、未課金
- payment_failed: 支払い失敗、または請求失敗

本アプリの運用に合わせて、同内容の手動実行SQLを
以下に分割して用意する。
- `migrations/sql/q8r9s0t1u2v3_add_trial_expired_and_payment_failed_billing_status_confirm.sql`
- `migrations/sql/q8r9s0t1u2v3_add_trial_expired_and_payment_failed_billing_status_upgrade.sql`
- `migrations/sql/q8r9s0t1u2v3_add_trial_expired_and_payment_failed_billing_status_downgrade.sql`

注意:
- DBへの実反映はAlembicコマンドではなくSQLファイルを手動実行して行う。
- このmigrationファイルは、手動実行SQLと同じ変更内容を残すための記録として作成する。
- 現行DBでは `ck_billings_billing_status` が以下6値を許可している前提。
  free / early_payment / active / past_due / canceling / canceled
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'q8r9s0t1u2v3'
down_revision: Union[str, None] = 'p7q8r9s0t1u2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_BILLING_STATUS_COMMENT = (
    "Billing status: free (無料トライアル), "
    "early_payment (早期支払い完了・無料期間中), "
    "active (課金中), "
    "past_due (互換用の支払い対応必要状態), "
    "trial_expired (無料期間終了・未課金), "
    "payment_failed (支払い失敗), "
    "canceling (キャンセル予定), "
    "canceled (キャンセル済み)"
)

OLD_BILLING_STATUS_COMMENT = (
    "Billing status: free (無料トライアル), "
    "early_payment (早期支払い完了・無料期間中), "
    "active (課金中), "
    "past_due (支払い遅延), "
    "canceling (キャンセル予定), "
    "canceled (キャンセル済み)"
)


def upgrade() -> None:
    """BillingStatus enumにtrial_expired/payment_failedを追加する。"""

    # 現行CHECK制約は6値のみ許可しているため、enum型変更前に削除する。
    # 変更後はtrial_expired/payment_failedを含む8値のCHECK制約として再作成する。
    op.execute("""
        ALTER TABLE billings
        DROP CONSTRAINT IF EXISTS ck_billings_billing_status
    """)

    op.execute("ALTER TABLE billings ALTER COLUMN billing_status DROP DEFAULT")

    op.execute("ALTER TYPE billingstatus RENAME TO billingstatus_old")

    op.execute("""
        CREATE TYPE billingstatus AS ENUM(
            'free',
            'early_payment',
            'active',
            'past_due',
            'trial_expired',
            'payment_failed',
            'canceling',
            'canceled'
        )
    """)

    op.execute("""
        ALTER TABLE billings
        ALTER COLUMN billing_status
        TYPE billingstatus
        USING billing_status::text::billingstatus
    """)

    op.execute("ALTER TABLE billings ALTER COLUMN billing_status SET DEFAULT 'free'::billingstatus")

    op.execute("DROP TYPE billingstatus_old")

    op.execute("""
        ALTER TABLE billings
        ADD CONSTRAINT ck_billings_billing_status
        CHECK (billing_status::text = ANY (ARRAY[
            'free'::character varying::text,
            'early_payment'::character varying::text,
            'active'::character varying::text,
            'past_due'::character varying::text,
            'trial_expired'::character varying::text,
            'payment_failed'::character varying::text,
            'canceling'::character varying::text,
            'canceled'::character varying::text
        ]))
    """)

    op.execute(f"""
        COMMENT ON COLUMN billings.billing_status IS
        '{NEW_BILLING_STATUS_COMMENT}'
    """)


def downgrade() -> None:
    """
    BillingStatus enumからtrial_expired/payment_failedを削除する。

    互換性維持のため、既存のtrial_expired/payment_failedデータは
    downgrade前にpast_dueへ戻す。
    """

    # downgrade後のCHECK制約ではtrial_expired/payment_failedを許可しないため、
    # 先に後方互換用のpast_dueへ戻す。
    op.execute("""
        UPDATE billings
        SET billing_status = 'past_due'
        WHERE billing_status IN ('trial_expired', 'payment_failed')
    """)

    # 8値のCHECK制約を削除し、enum型を6値へ戻したあと、
    # 現行DBと同じ6値のCHECK制約を再作成する。
    op.execute("""
        ALTER TABLE billings
        DROP CONSTRAINT IF EXISTS ck_billings_billing_status
    """)

    op.execute("ALTER TABLE billings ALTER COLUMN billing_status DROP DEFAULT")

    op.execute("ALTER TYPE billingstatus RENAME TO billingstatus_new")

    op.execute("""
        CREATE TYPE billingstatus AS ENUM(
            'free',
            'early_payment',
            'active',
            'past_due',
            'canceling',
            'canceled'
        )
    """)

    op.execute("""
        ALTER TABLE billings
        ALTER COLUMN billing_status
        TYPE billingstatus
        USING billing_status::text::billingstatus
    """)

    op.execute("ALTER TABLE billings ALTER COLUMN billing_status SET DEFAULT 'free'::billingstatus")

    op.execute("DROP TYPE billingstatus_new")

    op.execute("""
        ALTER TABLE billings
        ADD CONSTRAINT ck_billings_billing_status
        CHECK (billing_status::text = ANY (ARRAY[
            'free'::character varying::text,
            'early_payment'::character varying::text,
            'active'::character varying::text,
            'past_due'::character varying::text,
            'canceling'::character varying::text,
            'canceled'::character varying::text
        ]))
    """)

    op.execute(f"""
        COMMENT ON COLUMN billings.billing_status IS
        '{OLD_BILLING_STATUS_COMMENT}'
    """)
