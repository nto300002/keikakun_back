"""furigana_segmentation

Revision ID: 8btga4fq6fym
Revises: c6r6a2uqmvic
Create Date: 2025-10-21 00:00:04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8btga4fq6fym'
down_revision: Union[str, None] = 'c6r6a2uqmvic'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # welfare_recipientsテーブルにfirst_name_furiganaとlast_name_furiganaカラムを追加
    op.add_column('welfare_recipients', sa.Column('first_name_furigana', sa.String(length=255), nullable=True))
    op.add_column('welfare_recipients', sa.Column('last_name_furigana', sa.String(length=255), nullable=True))

    # 既存のfuriganaカラムからデータを分割して移行
    op.execute("""
        UPDATE welfare_recipients
        SET
            last_name_furigana = SPLIT_PART(furigana, ' ', 1),
            first_name_furigana = SPLIT_PART(furigana, ' ', 2)
        WHERE furigana IS NOT NULL AND furigana != ''
    """)

    # furiganaカラムを削除
    op.drop_column('welfare_recipients', 'furigana')


def downgrade() -> None:
    # furiganaカラムを追加
    op.add_column('welfare_recipients', sa.Column('furigana', sa.String(length=255), nullable=True))

    # データを結合して戻す
    op.execute("""
        UPDATE welfare_recipients
        SET furigana = last_name_furigana || ' ' || first_name_furigana
        WHERE last_name_furigana IS NOT NULL AND first_name_furigana IS NOT NULL
    """)

    # 分割されたカラムを削除
    op.drop_column('welfare_recipients', 'last_name_furigana')
    op.drop_column('welfare_recipients', 'first_name_furigana')
