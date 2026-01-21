#!/usr/bin/env python3
"""notification_preferencesカラムの存在確認スクリプト"""

from app.db.session import SyncSessionLocal
from sqlalchemy import text
import json

db = SyncSessionLocal()
try:
    # カラムの存在確認
    result = db.execute(text(
        "SELECT column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_name = 'staffs' AND column_name = 'notification_preferences';"
    ))
    row = result.fetchone()

    if row:
        print(f"✅ Column found: {row[0]}, Type: {row[1]}")
    else:
        print("❌ notification_preferences column NOT found")

    # 既存データのサンプルを確認
    result = db.execute(text("SELECT id, notification_preferences FROM staffs LIMIT 1;"))
    staff = result.fetchone()

    if staff:
        print(f"\n📊 Sample data for staff ID {staff[0]}:")
        print(json.dumps(staff[1], ensure_ascii=False, indent=2))
    else:
        print("\n⚠️ No staff records found")

except Exception as e:
    print(f"❌ Error: {e}")
finally:
    db.close()
