"""add_assessment_tables

Revision ID: m9n8x7y6z5a4
Revises: 7kk4eluc4xjl
Create Date: 2025-10-21 10:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'm9n8x7y6z5a4'
down_revision: Union[str, None] = '7kk4eluc4xjl'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum Types for assessment tables
    op.execute("""
        CREATE TYPE household AS ENUM ('same', 'separate')
    """)

    op.execute("""
        CREATE TYPE medical_care_insurance AS ENUM (
            'national_health_insurance', 'mutual_aid', 'social_insurance',
            'livelihood_protection', 'other'
        )
    """)

    op.execute("""
        CREATE TYPE aiding_type AS ENUM ('none', 'subsidized', 'full_exemption')
    """)

    op.execute("""
        CREATE TYPE work_conditions AS ENUM (
            'general_employment', 'part_time', 'transition_support',
            'continuous_support_a', 'continuous_support_b', 'main_employment', 'other'
        )
    """)

    op.execute("""
        CREATE TYPE work_outside_facility AS ENUM ('hope', 'not_hope', 'undecided')
    """)

    # Table: family_of_service_recipients
    op.create_table('family_of_service_recipients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('welfare_recipient_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('relationship', sa.Text(), nullable=False),
        sa.Column('household', sa.Enum('same', 'separate', name='household'), nullable=False),
        sa.Column('ones_health', sa.Text(), nullable=False),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('family_structure_chart', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['welfare_recipient_id'], ['welfare_recipients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Trigger for family_of_service_recipients
    op.execute("""
        CREATE TRIGGER update_family_of_service_recipients_updated_at
        BEFORE UPDATE ON family_of_service_recipients
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)

    # Table: welfare_services_used
    op.create_table('welfare_services_used',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('welfare_recipient_id', UUID(as_uuid=True), nullable=False),
        sa.Column('office_name', sa.Text(), nullable=False),
        sa.Column('starting_day', sa.Date(), nullable=False),
        sa.Column('amount_used', sa.Text(), nullable=False),
        sa.Column('service_name', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['welfare_recipient_id'], ['welfare_recipients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Trigger for welfare_services_used
    op.execute("""
        CREATE TRIGGER update_welfare_services_used_updated_at
        BEFORE UPDATE ON welfare_services_used
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)

    # Table: medical_matters
    op.create_table('medical_matters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('welfare_recipient_id', UUID(as_uuid=True), nullable=False),
        sa.Column('medical_care_insurance', sa.Enum(
            'national_health_insurance', 'mutual_aid', 'social_insurance',
            'livelihood_protection', 'other',
            name='medical_care_insurance'
        ), nullable=False),
        sa.Column('medical_care_insurance_other_text', sa.Text(), nullable=True),
        sa.Column('aiding', sa.Enum('none', 'subsidized', 'full_exemption', name='aiding_type'), nullable=False),
        sa.Column('history_of_hospitalization_in_the_past_2_years', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['welfare_recipient_id'], ['welfare_recipients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('welfare_recipient_id')
    )

    # Trigger for medical_matters
    op.execute("""
        CREATE TRIGGER update_medical_matters_updated_at
        BEFORE UPDATE ON medical_matters
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)

    # Table: history_of_hospital_visits
    op.create_table('history_of_hospital_visits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('medical_matters_id', sa.Integer(), nullable=False),
        sa.Column('disease', sa.Text(), nullable=False),
        sa.Column('frequency_of_hospital_visits', sa.Text(), nullable=False),
        sa.Column('symptoms', sa.Text(), nullable=False),
        sa.Column('medical_institution', sa.Text(), nullable=False),
        sa.Column('doctor', sa.Text(), nullable=False),
        sa.Column('tel', sa.Text(), nullable=False),
        sa.Column('taking_medicine', sa.Boolean(), nullable=False),
        sa.Column('date_started', sa.Date(), nullable=True),
        sa.Column('date_ended', sa.Date(), nullable=True),
        sa.Column('special_remarks', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['medical_matters_id'], ['medical_matters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Trigger for history_of_hospital_visits
    op.execute("""
        CREATE TRIGGER update_history_of_hospital_visits_updated_at
        BEFORE UPDATE ON history_of_hospital_visits
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)

    # Table: employment_related
    op.create_table('employment_related',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('welfare_recipient_id', UUID(as_uuid=True), nullable=False),
        sa.Column('created_by_staff_id', UUID(as_uuid=True), nullable=False),
        sa.Column('work_conditions', sa.Enum(
            'general_employment', 'part_time', 'transition_support',
            'continuous_support_a', 'continuous_support_b', 'main_employment', 'other',
            name='work_conditions'
        ), nullable=False),
        sa.Column('regular_or_part_time_job', sa.Boolean(), nullable=False),
        sa.Column('employment_support', sa.Boolean(), nullable=False),
        sa.Column('work_experience_in_the_past_year', sa.Boolean(), nullable=False),
        sa.Column('suspension_of_work', sa.Boolean(), nullable=False),
        sa.Column('qualifications', sa.Text(), nullable=True),
        sa.Column('main_places_of_employment', sa.Text(), nullable=True),
        sa.Column('general_employment_request', sa.Boolean(), nullable=False),
        sa.Column('desired_job', sa.Text(), nullable=True),
        sa.Column('special_remarks', sa.Text(), nullable=True),
        sa.Column('work_outside_the_facility', sa.Enum('hope', 'not_hope', 'undecided', name='work_outside_facility'), nullable=False),
        sa.Column('special_note_about_working_outside_the_facility', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['welfare_recipient_id'], ['welfare_recipients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('welfare_recipient_id')
    )

    # Trigger for employment_related
    op.execute("""
        CREATE TRIGGER update_employment_related_updated_at
        BEFORE UPDATE ON employment_related
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)

    # Table: issue_analyses
    op.create_table('issue_analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('welfare_recipient_id', UUID(as_uuid=True), nullable=False),
        sa.Column('created_by_staff_id', UUID(as_uuid=True), nullable=False),
        sa.Column('what_i_like_to_do', sa.Text(), nullable=True),
        sa.Column('im_not_good_at', sa.Text(), nullable=True),
        sa.Column('the_life_i_want', sa.Text(), nullable=True),
        sa.Column('the_support_i_want', sa.Text(), nullable=True),
        sa.Column('points_to_keep_in_mind_when_providing_support', sa.Text(), nullable=True),
        sa.Column('future_dreams', sa.Text(), nullable=True),
        sa.Column('other', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['welfare_recipient_id'], ['welfare_recipients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('welfare_recipient_id')
    )

    # Trigger for issue_analyses
    op.execute("""
        CREATE TRIGGER update_issue_analyses_updated_at
        BEFORE UPDATE ON issue_analyses
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)


def downgrade() -> None:
    op.drop_table('issue_analyses')
    op.drop_table('employment_related')
    op.drop_table('history_of_hospital_visits')
    op.drop_table('medical_matters')
    op.drop_table('welfare_services_used')
    op.drop_table('family_of_service_recipients')

    op.execute('DROP TYPE IF EXISTS work_outside_facility')
    op.execute('DROP TYPE IF EXISTS work_conditions')
    op.execute('DROP TYPE IF EXISTS aiding_type')
    op.execute('DROP TYPE IF EXISTS medical_care_insurance')
    op.execute('DROP TYPE IF EXISTS household')
