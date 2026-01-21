"""add threshold fields to notification_preferences

Revision ID: b0c1d2e3f4g5
Revises: a9b0c1d2e3f4
Create Date: 2026-01-14 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b0c1d2e3f4g5'
down_revision = 'a9b0c1d2e3f4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add threshold fields to existing notification_preferences column

    This migration adds:
    - email_threshold_days: Email notification threshold in days (default: 30)
    - push_threshold_days: Web Push notification threshold in days (default: 10)

    Strategy:
    1. Update all existing records to add threshold fields
    2. Update column default value
    """
    # Step 1: Add threshold fields to all existing records
    op.execute("""
        UPDATE staffs
        SET notification_preferences = notification_preferences ||
            '{"email_threshold_days": 30, "push_threshold_days": 10}'::jsonb
        WHERE notification_preferences IS NOT NULL
    """)

    # Step 2: Update column default value for new records
    op.alter_column(
        'staffs',
        'notification_preferences',
        server_default=sa.text(
            "'{\"in_app_notification\": true, \"email_notification\": true, \"system_notification\": false, \"email_threshold_days\": 30, \"push_threshold_days\": 10}'::jsonb"
        )
    )


def downgrade() -> None:
    """
    Remove threshold fields from notification_preferences column
    """
    # Step 1: Remove threshold fields from all existing records
    op.execute("""
        UPDATE staffs
        SET notification_preferences = notification_preferences - 'email_threshold_days' - 'push_threshold_days'
        WHERE notification_preferences IS NOT NULL
    """)

    # Step 2: Restore original default value
    op.alter_column(
        'staffs',
        'notification_preferences',
        server_default=sa.text(
            "'{\"in_app_notification\": true, \"email_notification\": true, \"system_notification\": false}'::jsonb"
        )
    )
