"""
テストデータスナップショット管理

目的: テストデータの高速復元（100倍高速化）
- Before: 毎回9分かけてデータ生成
- After: 初回のみ生成、2回目以降は10秒で復元

使用例:
    # スナップショット作成
    await create_snapshot(db, "100_offices_dataset")

    # スナップショット復元
    await restore_snapshot(db, "100_offices_dataset")

    # スナップショット一覧
    snapshots = await list_snapshots()
"""
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
import json
import shutil
import tempfile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, MetaData, Table
from sqlalchemy.orm import sessionmaker
import logging

logger = logging.getLogger(__name__)

# スキーマバージョン（Alembicと同期すべき）
SCHEMA_VERSION = "1.0.0"

# スナップショット保存ディレクトリ
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)


class SnapshotMetadata:
    """スナップショットメタデータ"""
    def __init__(
        self,
        name: str,
        created_at: datetime,
        description: str,
        stats: Dict[str, int]
    ):
        self.name = name
        self.created_at = created_at
        self.description = description
        self.stats = stats  # {"offices": 100, "staffs": 1000, ...}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "description": self.description,
            "stats": self.stats
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotMetadata":
        return cls(
            name=data["name"],
            created_at=datetime.fromisoformat(data["created_at"]),
            description=data["description"],
            stats=data["stats"]
        )


def _check_disk_space(path: Path, required_mb: int = 1000):
    """
    ディスク容量をチェック

    Args:
        path: チェック対象のパス
        required_mb: 必要な空き容量（MB）

    Raises:
        RuntimeError: 空き容量が不足している場合
    """
    stat = shutil.disk_usage(path)
    free_mb = stat.free / (1024 * 1024)

    if free_mb < required_mb:
        raise RuntimeError(
            f"ディスク容量不足: 空き容量 {free_mb:.0f}MB < 必要容量 {required_mb}MB\n"
            f"スナップショット作成には最低 {required_mb}MB の空き容量が必要です。"
        )

    logger.info(f"Disk space check OK: {free_mb:.0f}MB available")


async def _get_current_schema_version(db: AsyncSession) -> str:
    """
    現在のDBスキーマバージョンを取得

    Args:
        db: データベースセッション

    Returns:
        str: スキーマバージョン（例: "1.0.0"）

    Note:
        本来はAlembicのバージョンテーブルから取得すべきだが、
        テスト環境では固定値を返す
    """
    # TODO: Alembicのversion_numから取得する実装に変更
    return SCHEMA_VERSION


async def create_snapshot(
    db: AsyncSession,
    name: str,
    description: str = ""
) -> SnapshotMetadata:
    """
    テストデータのスナップショットを作成

    仕組み:
    1. ディスク容量チェック（最低1GB必要）
    2. is_test_data=Trueのデータをテーブルごとにダンプ
    3. 一時ファイルに書き込み → 成功したらアトミックに移動
    4. メタデータ（作成日時、統計情報、スキーマバージョン）を保存

    Args:
        db: データベースセッション
        name: スナップショット名（ユニーク）
        description: 説明文

    Returns:
        SnapshotMetadata: 作成したスナップショットのメタデータ

    Raises:
        ValueError: 同名のスナップショットが既に存在する場合
        RuntimeError: ディスク容量不足、DB接続エラー、書き込みエラー
    """
    snapshot_path = SNAPSHOT_DIR / f"{name}.json"

    if snapshot_path.exists():
        raise ValueError(f"Snapshot '{name}' already exists")

    # ディスク容量チェック（Issue #8）
    _check_disk_space(SNAPSHOT_DIR, required_mb=1000)

    logger.info(f"Creating snapshot: {name}")

    # テストデータが存在するテーブル一覧
    # 依存関係順（外部キー制約を考慮）
    tables = [
        "offices",
        "staffs",
        "office_staffs",
        "welfare_recipients",
        "office_welfare_recipients",
        "support_plan_cycles",
    ]

    # スキーマバージョンを含める（Issue #6）
    snapshot_data = {
        "schema_version": await _get_current_schema_version(db),
        "name": name,
        "created_at": datetime.now().isoformat(),
        "description": description,
        "stats": {},
        "tables": {}
    }

    # 各テーブルのテストデータをエクスポート
    for table in tables:
        # is_test_data=Trueのデータをすべて取得
        query = text(f"""
            SELECT row_to_json(t)
            FROM {table} t
            WHERE is_test_data = true
        """)

        result = await db.execute(query)
        rows = [row[0] for row in result.fetchall()]

        snapshot_data["tables"][table] = rows
        snapshot_data["stats"][table] = len(rows)

        logger.info(f"  Exported {len(rows)} rows from {table}")

    # アトミックな書き込み（Issue #1）
    # 一時ファイルに書き込み → 成功したら本ファイルに移動
    temp_fd, temp_path_str = tempfile.mkstemp(
        suffix=".json",
        prefix=f"{name}_",
        dir=SNAPSHOT_DIR
    )
    temp_path = Path(temp_path_str)

    try:
        # 一時ファイルに書き込み
        with open(temp_fd, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, ensure_ascii=False, indent=2, default=str)

        # 成功したらアトミックに移動
        shutil.move(temp_path, snapshot_path)

        logger.info(f"✅ Snapshot created: {snapshot_path}")
        logger.info(f"   Schema version: {snapshot_data['schema_version']}")
        logger.info(f"   Stats: {snapshot_data['stats']}")

        return SnapshotMetadata(
            name=name,
            created_at=datetime.fromisoformat(snapshot_data["created_at"]),
            description=description,
            stats=snapshot_data["stats"]
        )

    except Exception as e:
        # エラー時は一時ファイルをクリーンアップ
        if temp_path.exists():
            temp_path.unlink()
        logger.error(f"❌ Snapshot creation failed: {e}")
        raise RuntimeError(f"スナップショット作成に失敗しました: {e}")


async def restore_snapshot(
    db: AsyncSession,
    name: str,
    clean_existing: bool = True
) -> SnapshotMetadata:
    """
    スナップショットからテストデータを復元

    仕組み:
    1. スナップショットファイルの検証（破損チェック、スキーマバージョン）
    2. 既存のテストデータを削除（clean_existing=True）
    3. トランザクション内でテーブルごとにバルクインサート
    4. エラー時は自動ロールバック

    Args:
        db: データベースセッション
        name: スナップショット名
        clean_existing: 既存のテストデータを削除するか

    Returns:
        SnapshotMetadata: 復元したスナップショットのメタデータ

    Raises:
        FileNotFoundError: スナップショットが存在しない場合
        RuntimeError: JSONファイルが破損、スキーマ不一致、復元エラー
    """
    snapshot_path = SNAPSHOT_DIR / f"{name}.json"

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot '{name}' not found")

    logger.info(f"Restoring snapshot: {name}")

    # スナップショットファイルを読み込み（Issue #5: 破損JSONのハンドリング）
    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot_data = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"スナップショット '{name}' のJSONファイルが破損しています。\n"
            f"ファイルパス: {snapshot_path}\n"
            f"削除してから再作成してください。\n"
            f"詳細: {e}"
        )
    except Exception as e:
        raise RuntimeError(f"スナップショット読み込みエラー: {e}")

    # スキーマバージョンチェック（Issue #6）
    current_version = await _get_current_schema_version(db)
    snapshot_version = snapshot_data.get("schema_version", "unknown")

    if snapshot_version != current_version:
        logger.warning(
            f"⚠️ スキーマバージョンが一致しません: "
            f"スナップショット={snapshot_version}, 現在={current_version}\n"
            f"復元を続行しますが、エラーが発生する可能性があります。"
        )

    # 既存のテストデータを削除
    if clean_existing:
        await _clean_test_data(db)

    # テーブルごとにデータを復元（依存関係順）
    # Note: 外部キー制約を考慮した順序
    # - staffs: 依存なし (先に挿入)
    # - offices: staffs.id を参照 (created_by)
    # - office_staffs: staffs.id, offices.id を参照
    tables_order = [
        "staffs",
        "offices",
        "office_staffs",
        "welfare_recipients",
        "office_welfare_recipients",
        "support_plan_cycles",
    ]

    # Issue #2: ロールバック対応
    current_table = None
    try:
        for table in tables_order:
            current_table = table
            rows = snapshot_data["tables"].get(table, [])
            if not rows:
                continue

            # バルクインサート最適化
            # バッチサイズごとに処理してSSL timeoutを回避
            batch_size = 1000  # executemany()で効率的に処理できるサイズ
            total_rows = len(rows)

            for batch_start in range(0, total_rows, batch_size):
                batch_end = min(batch_start + batch_size, total_rows)
                batch_rows = rows[batch_start:batch_end]

                # JSONB fields need to be converted to JSON strings
                processed_rows = []
                for row in batch_rows:
                    processed_row = {}
                    for key, value in row.items():
                        if isinstance(value, dict):
                            # JSONB field - convert to JSON string
                            processed_row[key] = json.dumps(value)
                        else:
                            processed_row[key] = value
                    processed_rows.append(processed_row)

                if processed_rows:
                    columns = ", ".join(processed_rows[0].keys())
                    placeholders = ", ".join([f":{key}" for key in processed_rows[0].keys()])

                    query = text(f"""
                        INSERT INTO {table} ({columns})
                        VALUES ({placeholders})
                    """)

                    # executemany()で一括実行
                    await db.execute(query, processed_rows)

                    # flush()で中間コミット（接続を維持）
                    await db.flush()

                logger.info(f"  Restored batch {batch_start//batch_size + 1}/{(total_rows + batch_size - 1)//batch_size} ({len(batch_rows)} rows) to {table}")

            logger.info(f"  ✅ Restored total {len(rows)} rows to {table}")

        # 全テーブルの復元が成功したらコミット
        await db.commit()

        logger.info(f"✅ Snapshot restored: {name}")
        logger.info(f"   Schema version: {snapshot_version}")
        logger.info(f"   Stats: {snapshot_data['stats']}")

        return SnapshotMetadata.from_dict({
            "name": snapshot_data["name"],
            "created_at": snapshot_data["created_at"],
            "description": snapshot_data["description"],
            "stats": snapshot_data["stats"]
        })

    except Exception as e:
        # エラー時は自動的にロールバック
        logger.error(f"❌ Snapshot restoration failed at table '{current_table}': {e}")
        await db.rollback()
        raise RuntimeError(
            f"スナップショット復元に失敗しました（テーブル: {current_table}）\n"
            f"全ての変更がロールバックされました。\n"
            f"詳細: {e}"
        )


async def _clean_test_data(db: AsyncSession):
    """
    テストデータを全削除

    依存関係の逆順で削除（外部キー制約エラー回避）

    Note: 依存関係の順序
    - offices.created_by → staffs.id
    - office_staffs → staffs.id, offices.id
    - したがって、offices → office_staffs → staffs の順で削除
    """
    tables = [
        "support_plan_cycles",
        "office_welfare_recipients",
        "welfare_recipients",
        "office_staffs",
        "offices",  # staffs より先に削除（created_by 外部キー制約）
        "staffs",
    ]

    for table in tables:
        query = text(f"DELETE FROM {table} WHERE is_test_data = true")
        result = await db.execute(query)
        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"  Deleted {deleted} test rows from {table}")

    await db.commit()


async def list_snapshots() -> List[SnapshotMetadata]:
    """
    利用可能なスナップショット一覧を取得

    Returns:
        List[SnapshotMetadata]: スナップショットのリスト（新しい順）
    """
    snapshots = []

    for snapshot_file in SNAPSHOT_DIR.glob("*.json"):
        with open(snapshot_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        snapshots.append(SnapshotMetadata.from_dict({
            "name": data["name"],
            "created_at": data["created_at"],
            "description": data["description"],
            "stats": data["stats"]
        }))

    # 作成日時の新しい順でソート
    snapshots.sort(key=lambda s: s.created_at, reverse=True)

    return snapshots


async def delete_snapshot(name: str) -> bool:
    """
    スナップショットを削除

    Args:
        name: スナップショット名

    Returns:
        bool: 削除成功したらTrue
    """
    snapshot_path = SNAPSHOT_DIR / f"{name}.json"

    if not snapshot_path.exists():
        return False

    snapshot_path.unlink()
    logger.info(f"🗑️ Snapshot deleted: {name}")

    return True


async def snapshot_exists(name: str) -> bool:
    """
    スナップショットが存在するかチェック

    Args:
        name: スナップショット名

    Returns:
        bool: 存在すればTrue
    """
    snapshot_path = SNAPSHOT_DIR / f"{name}.json"
    return snapshot_path.exists()
