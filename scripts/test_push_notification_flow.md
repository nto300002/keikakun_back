# Web Push通知の動作確認手順

## 前提条件
- フロントエンド: `http://localhost:3000` で起動中
- バックエンド: `http://localhost:8000` で起動中
- Chrome/Firefox/Safari などのモダンブラウザ

---

## 1. サイトデータクリア後の動作確認

### Step 1-1: サイトデータをクリア
1. Chrome DevToolsを開く（F12）
2. Application タブ → Storage → Clear site data
3. 「Clear site data」ボタンをクリック
4. ページをリロード

### Step 1-2: ログイン
1. ログイン画面でログイン
2. ブラウザコンソールを確認:
   ```
   [Auto-subscribe] ...
   ```
   のログが表示される（エラーでもOK）

### Step 1-3: 通知設定画面で購読登録
1. プロフィール → 通知設定に移動
2. システム通知（Web Push）をONにする
3. ブラウザの通知許可ダイアログが表示される → 「許可」をクリック
4. トースト通知: **「システム通知を有効にしました」** が表示される
5. ブラウザコンソールを確認:
   ```
   [usePushNotification] Successfully subscribed
   ```
   のログが表示される

### Step 1-4: 購読データの確認
```bash
docker exec keikakun_app-backend-1 python3 scripts/debug_push_notification.py
```

**期待結果**:
```
総購読件数: 1件

📋 購読詳細:
   1. スタッフ: か 社長 (k***@gmail.com)
      購読ID: ...
      エンドポイント: https://fcm.googleapis.com/...
```

---

## 2. 購読解除の動作確認

### Step 2-1: システム通知をOFF
1. プロフィール → 通知設定に移動
2. システム通知（Web Push）をOFFにする
3. トースト通知: **「システム通知を無効にしました」** が表示される
4. エラーが表示されないこと

### Step 2-2: 購読データの確認
```bash
docker exec keikakun_app-backend-1 python3 scripts/debug_push_notification.py
```

**期待結果**:
```
総購読件数: 0件

⚠️  購読データが登録されていません
```

---

## 3. バッチ処理の動作確認

### Step 3-1: システム通知を再度ON
1. プロフィール → 通知設定に移動
2. システム通知（Web Push）をONにする
3. トースト通知: **「システム通知を有効にしました」** が表示される

### Step 3-2: ドライラン実行
```bash
docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py --dry-run
```

**期待結果**:
```
📊 実行結果:
   メール送信: 1件
   Web Push送信: 1件 ← 0件から1件に増えている
   Web Push失敗: 0件
```

### Step 3-3: 本番実行
```bash
docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py
```

**期待結果**:
```
📊 実行結果:
   メール送信: 1件
   Web Push送信: 1件
   Web Push失敗: 0件

✅ 通知が送信されました
```

### Step 3-4: ブラウザで通知を確認
1. ブラウザの通知センター/通知領域を確認
2. 「期限アラート（事務所TEST）」という通知が表示されている
3. 通知をクリックすると `/recipients?filter=deadline` に遷移する

---

## 4. エラーハンドリングの確認

### Case 4-1: 通知許可を拒否した場合
1. サイトデータをクリア
2. ログイン
3. プロフィール → 通知設定に移動
4. システム通知（Web Push）をONにする
5. ブラウザの通知許可ダイアログで「ブロック」をクリック
6. トースト通知:
   ```
   ブラウザの通知許可が拒否されています。ブラウザの設定から通知を許可してください
   ```

### Case 4-2: Service Workerが登録されていない状態でOFF
1. サイトデータをクリア
2. ログイン
3. プロフィール → 通知設定に移動
4. システム通知（Web Push）のトグルが既にOFFになっている
5. トグルをクリックしてONにする
6. 正常に購読が完了する（エラーが出ない）

---

## 5. iOS Safari PWA動作確認（iOS端末のみ）

### Step 5-1: PWA化
1. iOS SafariでWebアプリにアクセス
2. 「共有」ボタンをタップ
3. 「ホーム画面に追加」を選択
4. 追加したアイコンをタップしてアプリを起動

### Step 5-2: システム通知をON
1. プロフィール → 通知設定に移動
2. システム通知（Web Push）をONにする
3. iOSの通知許可ダイアログが表示される → 「許可」をタップ
4. トースト通知: **「システム通知を有効にしました」**

### Step 5-3: バッチ処理実行
```bash
docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py
```

### Step 5-4: iOS通知センターで確認
1. iOS通知センターを開く
2. 「期限アラート」の通知が表示されている
3. 通知をタップするとアプリが開く

---

## トラブルシューティング

### エラー: "PERMISSION_DENIED"
**原因**: ブラウザの通知許可が拒否されている

**解決策**:
1. ブラウザのアドレスバー左の🔒アイコンをクリック
2. サイトの設定 → 通知 → 「許可」に変更
3. ページをリロード
4. システム通知を再度ONにする

---

### エラー: "Service Worker not registered"
**原因**: Service Workerの登録に失敗している

**解決策**:
1. ブラウザコンソール（F12）で以下を実行:
   ```javascript
   navigator.serviceWorker.getRegistrations().then(registrations => {
     registrations.forEach(registration => registration.unregister());
   });
   ```
2. ページをリロード
3. システム通知を再度ONにする

---

### エラー: "Subscription not found"
**原因**: バックエンドに購読データがない

**解決策**:
1. システム通知を一度OFFにする
2. 再度ONにする
3. 購読データが再作成される

---

## デバッグコマンド一覧

```bash
# 購読データの確認
docker exec keikakun_app-backend-1 python3 scripts/debug_push_notification.py

# バッチ処理のドライラン
docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py --dry-run

# バッチ処理の本番実行
docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py

# バッチ処理の強制実行（休日でも実行）
docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py --force

# バックエンドログの確認
docker logs keikakun_app-backend-1 2>&1 | grep -i "push" | tail -20
```

---

**作成日**: 2026-01-19
