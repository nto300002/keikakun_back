# テストデータベース クリーンアップシステム

## 概要

このプロジェクトでは、**安全性を最優先**したテストデータベースクリーンアップシステムを実装しています。

### 二段階のクリーンアップ戦略

#### 1. 自動クリーンアップ（安全・推奨）
- **ファクトリ関数で生成されたデータのみ**を削除
- 本番環境では絶対に実行されない
- テスト実行前後に自動実行

#### 2. 手動クリーンアップ（強力・要注意）
- **全データ**を削除
- 確認プロンプト必須
- 緊急時のみ使用

## 自動クリーンアップの仕組み（安全）

### セッションレベルの安全なクリーンアップ

**場所**: `tests/conftest.py` + `tests/utils/safe_cleanup.py`

pytest実行時に自動的にファクトリ関数で生成されたテストデータのみをクリーンアップします。

**安全性の特徴:**
- ✅ ファクトリ関数の命名規則に基づいて識別
- ✅ TEST_DATABASE_URLが設定されている場合のみ実行
- ✅ 本番環境キーワード（prod, production等）を検出して実行拒否
- ✅ 誤実行しても影響範囲は限定的

```python
@pytest_asyncio.fixture(scope="session", autouse=True)
async def cleanup_database_session():
    """
    ファクトリ生成データのみを安全にクリーンアップ

    autouse=True により、pytest実行時に自動的に実行される
    """
```

### ファクトリ生成データの識別方法

conftest.pyのファクトリ関数で生成されるデータは以下の命名規則を持ちます：

```python
# Staff（スタッフ）
email LIKE '%@test.com'
email LIKE '%@example.com'
last_name LIKE '%テスト%'
full_name LIKE '%テスト%'

# Office（事業所）
name LIKE '%テスト事業所%'

# WelfareRecipient（福祉受給者）
first_name LIKE '%テスト%'
last_name LIKE '%テスト%'
```

これらのパターンに一致するデータのみが削除されます。

### 実行例

```bash
# テストを実行すると自動的に安全なクリーンアップが実行されます
docker-compose exec backend pytest tests/

# ログ出力例:
# 2025-11-07 01:47:52 [INFO] conftest - 🧪 Starting test session - safe cleanup...
# 2025-11-07 01:47:52 [INFO] safe_cleanup - 🧹 Safely cleaned up 25 factory-generated test records
# ... テスト実行 ...
# 2025-11-07 01:48:01 [INFO] conftest - 🧪 Test session completed - safe cleanup...
```

## 手動クリーンアップ（⚠️ 強力・要注意）

### ⚠️ 警告

このスクリプトは**全データを削除**します。以下の場合のみ使用してください：

- テストデータベースが汚染され、完全にリセットが必要な場合
- 大量の古いテストデータを一括削除したい場合
- 開発環境をクリーンな状態に戻したい場合

**絶対に本番環境では実行しないでください。**

### 安全性チェック

スクリプトは以下の安全性チェックを実行します：

1. ✅ TEST_DATABASE_URLが明示的に設定されているか
2. ✅ 本番環境のキーワード（prod, production, main, live, master）が含まれていないか
3. ✅ ユーザーが'DELETE ALL DATA'と正確に入力したか

### スクリプトの実行

```bash
docker-compose exec backend python scripts/cleanup_test_db.py
```

### 実行例（キャンセル）

```
======================================================================
⚠️  WARNING: DESTRUCTIVE OPERATION
======================================================================

This will DELETE ALL DATA from the following database:
  postgresql+psycopg://keikakun_dev:npg_gZbvU3s5YRAM@ep-muddy-smoke...

This operation cannot be undone.

Type 'DELETE ALL DATA' to confirm (or anything else to cancel): cancel

✅ Operation cancelled - no data was deleted
```

### 実行例（実行）

```
======================================================================
⚠️  WARNING: DESTRUCTIVE OPERATION
======================================================================

This will DELETE ALL DATA from the following database:
  postgresql+psycopg://keikakun_dev:npg_gZbvU3s5YRAM@ep-muddy-smoke...

This operation cannot be undone.

Type 'DELETE ALL DATA' to confirm (or anything else to cancel): DELETE ALL DATA

⚠️  Proceeding with deletion...

🔌 接続先: postgresql+psycopg://keikakun_dev:npg_gZbvU3s5YRAM...

🧹 データベースクリーンアップを開始...
  ✓ plan_deliverables: 3件削除
  ✓ support_plan_statuses: 4件削除
  ✓ support_plan_cycles: 1件削除
  ✓ offices: 1件削除
  ✓ staffs: 759件削除

==================================================
✅ データベースクリーンアップ完了
==================================================

合計削除数: 799件
```

## クリーンアップユーティリティ

### DatabaseCleanupクラス

**場所**: `tests/utils/db_cleanup.py`

プログラムから直接クリーンアップ機能を利用できます。

```python
from tests.utils.db_cleanup import db_cleanup

# テストデータのみを選択的に削除
result = await db_cleanup.delete_test_data(db_session)

# 全データを削除
result = await db_cleanup.truncate_all_tables(db_session)

# データベースの状態を確認
is_clean, counts = await db_cleanup.verify_clean_state(db_session)
```

## 削除されるテーブル（依存関係の順）

以下のテーブルが依存関係を考慮した順序で削除されます：

1. `plan_deliverables`
2. `support_plan_statuses`
3. `support_plan_cycles`
4. `calendar_event_series`
5. `calendar_events`
6. `office_calendar_accounts`
7. `notices`
8. `role_change_requests`
9. `office_welfare_recipients`
10. `welfare_recipients`
11. `office_staffs`
12. `offices`
13. `staffs`

## トランザクション管理

各テストは独立したトランザクション内で実行され、テスト終了時に自動的にロールバックされます。

```python
@pytest_asyncio.fixture(scope="function")
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    ネストされたトランザクション（セーブポイント）を利用して、
    テスト終了時に全ての変更がロールバックされることを保証する。
    """
```

## テストベストプラクティス

### 1. テスト内でのデータ作成

```python
async def test_example(db_session: AsyncSession):
    # テストデータを作成
    staff = Staff(email="test@example.com", ...)
    db_session.add(staff)
    await db_session.flush()  # commit() ではなく flush() を使用

    # テスト実行
    # ...

    # テスト終了時に自動的にロールバックされる
```

### 2. fixture を使ったデータ作成

```python
async def test_with_fixture(
    db_session: AsyncSession,
    owner_user_with_office  # conftest.py で定義されたfixture
):
    # fixture で作成されたデータを使用
    # テスト終了時に自動的にクリーンアップされる
```

### 3. クリーンアップの確認

```python
async def test_cleanup_verification(db_session: AsyncSession):
    """データベースがクリーンな状態で開始されることを確認"""
    result = await db_session.execute(select(func.count()).select_from(Office))
    count = result.scalar()
    assert count == 0, f"Officesテーブルに{count}件のデータが残っています"
```

## トラブルシューティング

### テストデータが残っている場合

1. **手動クリーンアップを実行**:
   ```bash
   docker-compose exec backend python scripts/cleanup_test_db.py
   ```

2. **テスト実行ログを確認**:
   ```bash
   # ログレベルをINFOに設定してテスト実行
   docker-compose exec backend pytest tests/ -v --log-cli-level=INFO
   ```

3. **特定のテーブルを確認**:
   ```bash
   docker-compose exec backend python -c "
   from tests.utils.db_cleanup import db_cleanup
   import asyncio
   from app.db.session import get_db

   async def check():
       async for db in get_db():
           counts = await db_cleanup.get_table_counts(db)
           for table, count in counts.items():
               if count > 0:
                   print(f'{table}: {count}件')
           break

   asyncio.run(check())
   "
   ```

## CI/CD統合

GitHub ActionsやGitLab CIでテストを実行する場合、自動クリーンアップが有効になっているため、追加の設定は不要です。

```yaml
# .github/workflows/test.yml
- name: Run tests
  run: |
    docker-compose exec -T backend pytest tests/
    # 自動的にクリーンアップが実行されます
```

## 設定

### pytest.ini

```ini
[pytest]
pythonpath = . k_back
asyncio_mode = auto
log_cli = true
log_cli_level = INFO
addopts = -v --tb=short
```

### 環境変数

- `TEST_DATABASE_URL`: テスト用データベースのURL（必須）
- `DATABASE_URL`: フォールバック用のデータベースURL

## まとめ

- ✅ テスト実行前後に**自動的に**データベースがクリーンアップされます
- ✅ 手動クリーンアップスクリプトも利用可能
- ✅ トランザクションロールバックで各テストが独立
- ✅ 外部キー制約を考慮した正しい削除順序
- ✅ CI/CDで追加設定不要
