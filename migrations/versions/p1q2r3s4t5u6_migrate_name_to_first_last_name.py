"""migrate name to first_last_name

Revision ID: p1q2r3s4t5u6
Revises: o2b3c4d5e6f7
Create Date: 2025-11-03 14:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'p1q2r3s4t5u6'
down_revision = 'o2b3c4d5e6f7'
branch_labels = None
depends_on = None


def split_name(name: str) -> tuple[str, str]:
    """
    名前を姓と名に分割（シンプル版）

    ルール:
    1. スペース（全角・半角）で分割
    2. 複数パートがあれば: 最初を姓、残りを名
    3. 1パートのみ: 最初の1文字を姓、残りを名
    4. 1文字のみ: 姓は空、名にその文字
    """
    if not name or not name.strip():
        return ("", "")

    name = name.strip()

    # 全角スペースを半角に統一して分割
    parts = name.replace('　', ' ').split(' ')
    # 空文字を除外
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) == 0:
        return ("", "")
    elif len(parts) == 1:
        # 1パートのみ
        word = parts[0]
        if len(word) == 1:
            # 1文字のみ: 名のみ
            return ("", word)
        else:
            # 複数文字: 最初の1文字を姓、残りを名
            return (word[0], word[1:])
    else:
        # 複数パート: 最初を姓、残りを名
        last_name = parts[0]
        first_name = ' '.join(parts[1:])
        return (last_name, first_name)


def upgrade() -> None:
    """既存のnameデータをfirst_name/last_nameに移行"""
    connection = op.get_bind()

    # 移行対象のスタッフを取得
    result = connection.execute(text("""
        SELECT id, name
        FROM staffs
        WHERE name IS NOT NULL AND name <> ''
        AND (first_name IS NULL OR last_name IS NULL OR full_name IS NULL)
    """))

    staffs = result.fetchall()
    print(f"[Migration] Found {len(staffs)} staff records to migrate")

    # 各スタッフのnameを分割
    for staff in staffs:
        staff_id = staff[0]
        name = staff[1]

        last_name, first_name = split_name(name)

        # full_nameを生成
        if last_name and first_name:
            full_name = f"{last_name} {first_name}"
        else:
            full_name = last_name or first_name or ""

        # 更新
        connection.execute(
            text("""
                UPDATE staffs
                SET
                    last_name = :last_name,
                    first_name = :first_name,
                    full_name = :full_name
                WHERE id = :staff_id
            """),
            {
                "staff_id": staff_id,
                "last_name": last_name or "",
                "first_name": first_name or "",
                "full_name": full_name
            }
        )

        print(f"  [{staff_id}] '{name}' → last='{last_name}', first='{first_name}', full='{full_name}'")

    # full_nameにNOT NULL制約を追加
    op.alter_column('staffs', 'full_name',
                    existing_type=sa.String(length=255),
                    nullable=False,
                    server_default='')

    # インデックス作成
    op.create_index('ix_staffs_full_name', 'staffs', ['full_name'], unique=False)

    print("[Migration] Migration completed successfully")


def downgrade() -> None:
    """ロールバック"""
    # インデックス削除
    op.drop_index('ix_staffs_full_name', table_name='staffs')

    # NOT NULL制約解除
    op.alter_column('staffs', 'full_name',
                    existing_type=sa.String(length=255),
                    nullable=True,
                    server_default=None)

    # full_nameをnameにコピー
    connection = op.get_bind()
    connection.execute(text("""
        UPDATE staffs
        SET name = full_name
        WHERE full_name IS NOT NULL AND full_name <> ''
    """))

    print("[Migration] Rollback completed")
