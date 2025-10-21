"""recipients_detailed_data

Revision ID: lql9jwfmxenr
Revises: 5b3e28r3i79e
Create Date: 2025-10-21 00:00:08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'lql9jwfmxenr'
down_revision: Union[str, None] = '5b3e28r3i79e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum Types
    op.execute("""
        CREATE TYPE form_of_residence AS ENUM (
            'home_with_family', 'home_alone', 'group_home', 'institution', 'hospital', 'other'
        )
    """)
    op.execute("""
        CREATE TYPE means_of_transportation AS ENUM (
            'walk', 'bicycle', 'motorbike', 'car_self', 'car_transport',
            'public_transport', 'welfare_transport', 'other'
        )
    """)
    op.execute("""
        CREATE TYPE livelihood_protection AS ENUM (
            'not_receiving', 'receiving_with_allowance', 'receiving_without_allowance',
            'applying', 'planning'
        )
    """)
    op.execute("""
        CREATE TYPE disability_category AS ENUM (
            'physical_handbook', 'intellectual_handbook', 'mental_health_handbook',
            'disability_basic_pension', 'other_disability_pension', 'public_assistance'
        )
    """)
    op.execute("""
        CREATE TYPE physical_disability_type AS ENUM (
            'visual', 'hearing', 'limb', 'internal', 'other'
        )
    """)
    op.execute("""
        CREATE TYPE application_status AS ENUM (
            'acquired', 'applying', 'planning', 'not_applicable'
        )
    """)

    # Function to update the updated_at column
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # Table: service_recipient_details
    op.create_table('service_recipient_details',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('welfare_recipient_id', sa.UUID(), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('form_of_residence', sa.Enum(
            'home_with_family', 'home_alone', 'group_home', 'institution', 'hospital', 'other',
            name='form_of_residence'
        ), nullable=False),
        sa.Column('form_of_residence_other_text', sa.Text(), nullable=True),
        sa.Column('means_of_transportation', sa.Enum(
            'walk', 'bicycle', 'motorbike', 'car_self', 'car_transport',
            'public_transport', 'welfare_transport', 'other',
            name='means_of_transportation'
        ), nullable=False),
        sa.Column('means_of_transportation_other_text', sa.Text(), nullable=True),
        sa.Column('tel', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['welfare_recipient_id'], ['welfare_recipients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('welfare_recipient_id')
    )

    # Trigger for service_recipient_details
    op.execute("""
        CREATE TRIGGER update_service_recipient_details_updated_at
        BEFORE UPDATE ON service_recipient_details
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)

    # Table: emergency_contacts
    op.create_table('emergency_contacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('service_recipient_detail_id', sa.Integer(), nullable=False),
        sa.Column('first_name', sa.String(length=255), nullable=False),
        sa.Column('last_name', sa.String(length=255), nullable=False),
        sa.Column('first_name_furigana', sa.String(length=255), nullable=False),
        sa.Column('last_name_furigana', sa.String(length=255), nullable=False),
        sa.Column('relationship', sa.String(length=255), nullable=False),
        sa.Column('tel', sa.Text(), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['service_recipient_detail_id'], ['service_recipient_details.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Trigger for emergency_contacts
    op.execute("""
        CREATE TRIGGER update_emergency_contacts_updated_at
        BEFORE UPDATE ON emergency_contacts
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)

    # Table: disability_statuses
    op.create_table('disability_statuses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('welfare_recipient_id', sa.UUID(), nullable=False),
        sa.Column('disability_or_disease_name', sa.Text(), nullable=False),
        sa.Column('livelihood_protection', sa.Enum(
            'not_receiving', 'receiving_with_allowance', 'receiving_without_allowance',
            'applying', 'planning',
            name='livelihood_protection'
        ), nullable=False),
        sa.Column('special_remarks', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['welfare_recipient_id'], ['welfare_recipients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('welfare_recipient_id')
    )

    # Trigger for disability_statuses
    op.execute("""
        CREATE TRIGGER update_disability_statuses_updated_at
        BEFORE UPDATE ON disability_statuses
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)

    # Table: disability_details
    op.create_table('disability_details',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('disability_status_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.Enum(
            'physical_handbook', 'intellectual_handbook', 'mental_health_handbook',
            'disability_basic_pension', 'other_disability_pension', 'public_assistance',
            name='disability_category'
        ), nullable=False),
        sa.Column('grade_or_level', sa.Text(), nullable=True),
        sa.Column('physical_disability_type', sa.Enum(
            'visual', 'hearing', 'limb', 'internal', 'other',
            name='physical_disability_type'
        ), nullable=True),
        sa.Column('physical_disability_type_other_text', sa.Text(), nullable=True),
        sa.Column('application_status', sa.Enum(
            'acquired', 'applying', 'planning', 'not_applicable',
            name='application_status'
        ), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['disability_status_id'], ['disability_statuses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Trigger for disability_details
    op.execute("""
        CREATE TRIGGER update_disability_details_updated_at
        BEFORE UPDATE ON disability_details
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)


def downgrade() -> None:
    op.drop_table('disability_details')
    op.drop_table('disability_statuses')
    op.drop_table('emergency_contacts')
    op.drop_table('service_recipient_details')

    op.execute('DROP FUNCTION IF EXISTS update_updated_at_column()')

    op.execute('DROP TYPE IF EXISTS application_status')
    op.execute('DROP TYPE IF EXISTS physical_disability_type')
    op.execute('DROP TYPE IF EXISTS disability_category')
    op.execute('DROP TYPE IF EXISTS livelihood_protection')
    op.execute('DROP TYPE IF EXISTS means_of_transportation')
    op.execute('DROP TYPE IF EXISTS form_of_residence')
