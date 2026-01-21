"""add notification_preferences to staffs

Revision ID: a9b0c1d2e3f4
Revises: z8a9b0c1d2e3
Create Date: 2026-01-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a9b0c1d2e3f4'
down_revision = 'z8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add notification_preferences column to staffs table

    This column stores user preferences for three notification channels:
    - in_app_notification: Toast/Popover notifications (default: true)
    - email_notification: Daily batch email alerts (default: true)
    - system_notification: Web Push notifications (default: false)
    """
    op.add_column(
        'staffs',
        sa.Column(
            'notification_preferences',
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(
                "'{\"in_app_notification\": true, \"email_notification\": true, \"system_notification\": false}'::jsonb"
            )
        )
    )


def downgrade() -> None:
    """
    Remove notification_preferences column from staffs table
    """
    op.drop_column('staffs', 'notification_preferences')
