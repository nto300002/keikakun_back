"""
日本語エラーメッセージ定数

アプリケーション全体で使用される日本語のエラーメッセージを一元管理します。
メッセージは優先度別に整理されています。
"""

# ==========================================
# 認証関連 (auths.py)
# ==========================================

# ユーザー登録
AUTH_EMAIL_ALREADY_EXISTS = "このメールアドレスは既に登録されています"

# メール確認
AUTH_INVALID_TOKEN = "確認リンクが無効または期限切れです"
AUTH_USER_NOT_FOUND = "ユーザーが見つかりません"
AUTH_EMAIL_ALREADY_VERIFIED = "メールアドレスは既に確認済みです"
AUTH_EMAIL_VERIFIED = "メールアドレスの確認が完了しました"

# ログイン
AUTH_INCORRECT_CREDENTIALS = "メールアドレスまたはパスワードが正しくありません"
AUTH_EMAIL_NOT_VERIFIED = "メールアドレスの確認が完了していません"
AUTH_LOGIN_SUCCESS = "ログインしました"

# app_admin合言葉認証
AUTH_PASSPHRASE_REQUIRED = "合言葉を入力してください"
AUTH_INVALID_PASSPHRASE = "認証に失敗しました"  # セキュリティのため詳細は明かさない
AUTH_PASSPHRASE_NOT_SET = "合言葉が設定されていません。管理者に連絡してください。"

# 認証情報の更新
AUTH_INVALID_REFRESH_TOKEN = "認証情報が無効です"
AUTH_REFRESH_TOKEN_BLACKLISTED = "この認証情報は無効化されています。再度ログインしてください。"
AUTH_TOKEN_REFRESHED = "認証情報を更新しました"

# 2段階認証検証（ログイン時）
AUTH_INVALID_TEMPORARY_TOKEN = "一時認証情報が無効または期限切れです"
AUTH_MFA_NOT_CONFIGURED = "2段階認証が正しく設定されていません"
AUTH_INVALID_MFA_CODE = "認証コードまたはリカバリコードが正しくありません"
AUTH_MFA_VERIFICATION_SUCCESS = "2段階認証に成功しました"

# ログアウト
AUTH_LOGOUT_SUCCESS = "ログアウトしました"

# パスワードリセット
AUTH_PASSWORD_RESET_EMAIL_SENT = "パスワードリセット用のメールを送信しました。メールをご確認ください。"
AUTH_RESET_TOKEN_VALID = "確認リンクは有効です"
AUTH_RESET_TOKEN_INVALID_OR_EXPIRED = "確認リンクが無効または期限切れです。新しい確認リンクを発行してください。"
AUTH_RESET_TOKEN_ALREADY_USED = "この確認リンクは既に使用されています。新しい確認リンクを発行してください。"
AUTH_PASSWORD_RESET_SUCCESS = "パスワードが正常にリセットされました。新しいパスワードでログインしてください。"
AUTH_PASSWORD_RESET_FAILED = "パスワードリセットに失敗しました。時間をおいて再度お試しください。"
AUTH_PASSWORD_BREACHED = "このパスワードは過去のデータ侵害で流出しています。別のパスワードを選択してください。"
AUTH_TOKEN_INVALIDATED_BY_PASSWORD_CHANGE = "パスワードが変更されたため、この認証情報は無効化されました。再度ログインしてください。"

# レート制限
AUTH_RATE_LIMIT_EXCEEDED = "操作回数が多すぎます。しばらくしてから再度お試しください。"

# セキュリティ
SECURITY_REQUEST_EXPIRED = "画面の有効期限が切れました。ページを再読み込みして、もう一度お試しください。"

# ==========================================
# 権限関連 (deps.py)
# ==========================================

PERM_CREDENTIALS_INVALID = "認証情報を検証できません"
PERM_MANAGER_OR_OWNER_REQUIRED = "管理者または事業所管理者の権限が必要です"
PERM_OWNER_REQUIRED = "事業所管理者の権限が必要です"
PERM_OFFICE_REQUIRED = "スタッフは事業所に所属している必要があります"
PERM_OPERATION_FORBIDDEN = "この操作を行う権限がありません。"
PERM_OPERATION_FORBIDDEN_GENERIC = "この操作を実行する権限がありません"
PERM_MANAGER_OR_OWNER_APPROVE = "管理者または事業所管理者のみが申請を承認できます"
PERM_MANAGER_OR_OWNER_REJECT = "管理者または事業所管理者のみが申請を却下できます"
PERM_ACCOUNT_DELETED = "このアカウントは削除されています"

# ==========================================
# スタッフ管理関連 (staffs.py)
# ==========================================

STAFF_NOT_FOUND = "スタッフが見つかりません"
STAFF_ALREADY_DELETED = "このスタッフは既に削除されています"
STAFF_CANNOT_DELETE_SELF = "自分自身は削除できません"
STAFF_CANNOT_DELETE_LAST_OWNER = "最後のOwnerは削除できません"
STAFF_DIFFERENT_OFFICE = "異なる事務所のスタッフは削除できません"
STAFF_DELETED_SUCCESS = "スタッフを削除しました"
STAFF_DELETE_FAILED = "スタッフの削除に失敗しました: {error}"

# ==========================================
# 2段階認証関連 (mfa.py)
# ==========================================

MFA_ALREADY_ENABLED = "2段階認証は既に有効になっています"
MFA_NOT_ENROLLED = "2段階認証が登録されていません"
MFA_INVALID_CODE = "認証コードが正しくありません"
MFA_VERIFICATION_SUCCESS = "2段階認証の確認に成功しました"
MFA_NOT_ENABLED = "2段階認証は有効になっていません"
MFA_INCORRECT_PASSWORD = "パスワードが正しくありません"
MFA_DISABLED_SUCCESS = "2段階認証を無効にしました"
MFA_ENABLED_SUCCESS = "2段階認証を有効にしました"

# ==========================================
# 福祉受給者関連 (welfare_recipients.py)
# ==========================================

RECIPIENT_OFFICE_REQUIRED = "利用者を作成するには事業所に所属する必要があります"
RECIPIENT_MUST_BE_IN_OFFICE = "事業所に所属している必要があります"
RECIPIENT_REQUEST_PENDING = "申請を作成しました。承認待ちです"
RECIPIENT_CREATE_FAILED = "利用者の作成に失敗しました: {error}"
RECIPIENT_UPDATE_FAILED = "利用者の更新に失敗しました: {error}"
RECIPIENT_DELETE_FAILED = "利用者の削除に失敗しました"
RECIPIENT_DELETED = "利用者を削除しました"
RECIPIENT_DISABILITY_CATEGORY_MISSING = "手帳に関する情報が未入力です"
RECIPIENT_INVALID_INPUT = "無効な入力値です"
RECIPIENT_REPAIR_SUPPORT_PLAN_FAILED = "個別支援計画の修復に失敗しました"
RECIPIENT_CATEGORY_MISSING = "障害詳細のカテゴリが未指定です。"
RECIPIENT_MUST_HAVE_OFFICE = "スタッフは事業所に所属している必要があります"
RECIPIENT_NOT_FOUND = "利用者が見つかりません"
RECIPIENT_ACCESS_DENIED = "この利用者にアクセスする権限がありません"
RECIPIENT_UPDATE_NOT_FOUND = "利用者の更新に失敗しました"
RECIPIENT_DELETED_SUCCESS = "利用者を削除しました"
RECIPIENT_REPAIR_PERMISSION_DENIED = "管理者または事業所管理者のみが個別支援計画の修復を実行できます"

# ==========================================
# 権限変更申請 (role_change_requests.py)
# ==========================================

ROLE_ALREADY_ASSIGNED = "既に{role}の権限を持っています"
ROLE_NO_OFFICE = "事業所に所属していません"
ROLE_REQUEST_NOT_FOUND = "申請が見つかりません"
ROLE_REQUEST_ALREADY_PROCESSED = "申請は既に{status}です"
ROLE_NO_PERMISSION_TO_APPROVE = "この申請を承認する権限がありません"
ROLE_NO_PERMISSION_TO_REJECT = "この申請を却下する権限がありません"
ROLE_CAN_ONLY_DELETE_OWN = "自分の申請のみ削除できます"
ROLE_CANNOT_DELETE_PROCESSED = "{status}状態の申請は削除できません"

# ==========================================
# 個別支援計画 (support_plans.py)
# ==========================================

SUPPORT_PLAN_INVALID_PARAMS = "パラメータの形式が正しくありません: {error}"
SUPPORT_PLAN_PDF_ONLY = "アップロードできるファイルはPDF形式のみです。"
SUPPORT_PLAN_UPLOAD_FAILED = "ファイルのアップロードに失敗しました。"
SUPPORT_PLAN_PRESIGNED_URL_FAILED = "署名付きURLの生成に失敗しました。"
SUPPORT_PLAN_INVALID_RECIPIENT_IDS = "利用者IDの形式が正しくありません"
SUPPORT_PLAN_INVALID_DELIVERABLE_TYPES = "成果物タイプの形式が正しくありません"
SUPPORT_PLAN_LIST_FAILED = "PDF一覧の取得に失敗しました"
SUPPORT_PLAN_MONITORING_ONLY = "モニタリング期限はモニタリング状態のみ設定できます。"
SUPPORT_PLAN_STATUS_NOT_FOUND = "状態ID {status_id} が見つかりません。"
SUPPORT_PLAN_NO_ACCESS = "この状態にアクセスする権限がありません。"
SUPPORT_PLAN_RECIPIENT_NOT_FOUND = "利用者ID {recipient_id} が見つかりません。"
SUPPORT_PLAN_NO_PERMISSION = "この利用者の個別支援計画にアクセスする権限がありません。"
SUPPORT_PLAN_CYCLE_NOT_FOUND = "計画サイクルID {cycle_id} が見つかりません。"
SUPPORT_PLAN_DELIVERABLE_NOT_FOUND = "成果物ID {deliverable_id} が見つかりません。"
SUPPORT_PLAN_NO_DELIVERABLE_ACCESS = "この成果物にアクセスする権限がありません。"
SUPPORT_PLAN_NO_DELIVERABLE_UPDATE_ACCESS = "この成果物を更新する権限がありません。"
SUPPORT_PLAN_NO_DELIVERABLE_DELETE_ACCESS = "この成果物を削除する権限がありません。"
SUPPORT_PLAN_EMPLOYEE_CANNOT_UPLOAD = "一般スタッフは個別支援計画のPDFを登録できません。管理者または事業所管理者に依頼してください。"
SUPPORT_PLAN_EMPLOYEE_CANNOT_DELETE = "一般スタッフは個別支援計画のPDFを削除できません。管理者または事業所管理者に依頼してください。"
SUPPORT_PLAN_NO_CYCLE_ACCESS = "このサイクルにアクセスする権限がありません。"
SUPPORT_PLAN_NO_OFFICE_PDF_ACCESS = "この事業所のPDFにアクセスする権限がありません"

# ==========================================
# 事業所関連 (offices.py, office_staff.py)
# ==========================================

OFFICE_USER_NOT_FOUND = "ユーザーが見つかりません"
OFFICE_OWNER_CANNOT_USE_ENDPOINT = "事業所管理者はこのエンドポイントを使用できません"
OFFICE_NOT_FOUND_FOR_USER = "所属している事業所が見つかりません。"
OFFICE_INFO_NOT_FOUND = "事業所情報が見つかりません。"
OFFICE_ALREADY_ASSOCIATED = "ユーザーは既に事業所に所属しています。"
OFFICE_NAME_ALREADY_EXISTS = "すでにその名前の事務所は登録されています。"
OFFICE_NOT_FOUND = "指定された事業所が見つかりません。"

# ==========================================
# カスタム例外クラス (exceptions.py)
# ==========================================

EXC_BAD_REQUEST = "申請内容が正しくありません"
EXC_NOT_FOUND = "見つかりません"
EXC_FORBIDDEN = "アクセスが拒否されました"
EXC_INTERNAL_ERROR = "サーバー内部エラーが発生しました"

# ==========================================
# バリデーション (schemas)
# ==========================================

# スタッフスキーマ
VALIDATION_CANNOT_REGISTER_AS_OWNER = "このエンドポイントから事業所管理者として登録できません"
VALIDATION_NAME_CANNOT_BE_EMPTY = "{field_name}は空にできません"
VALIDATION_NAME_TOO_LONG = "{field_name}は50文字以内にしてください"
VALIDATION_NAME_CANNOT_BE_ONLY_NUMBERS = "名前に数字のみは使用できません"
VALIDATION_NAME_INVALID_CHARACTERS = "名前に使用できない文字が含まれています（日本語のみ使用可能）"
VALIDATION_PASSWORD_TOO_SHORT = "パスワードは8文字以上である必要があります"
VALIDATION_PASSWORD_COMPLEXITY = "パスワードは次のうち少なくとも3つを含む必要があります: 英字小文字、大文字、数字、記号"

# カレンダーアカウント
VALIDATION_REMINDER_DAYS_POSITIVE = "リマインダー日数は正の整数である必要があります"
VALIDATION_CUSTOM_REMINDER_FORMAT = "カスタムリマインダー日数はカンマ区切りの正の整数である必要があります"
VALIDATION_MISSING_FIELD_IN_JSON = "設定ファイルに必要な項目がありません。Googleの設定画面から取得したファイルを確認してください。"
VALIDATION_INVALID_SERVICE_ACCOUNT_TYPE = "設定ファイルの内容が正しくありません。Googleの設定画面から取得したファイルを確認してください。"
VALIDATION_INVALID_JSON_FORMAT = "設定ファイルの形式が正しくありません: {error}"

# 福祉受給者
VALIDATION_BIRTH_DATE_FUTURE = "生年月日は未来の日付にできません"

# ダッシュボード
VALIDATION_ID_MUST_BE_UUID = "idは有効なUUIDである必要があります"

# ==========================================
# サービス層
# ==========================================

# ロール変更サービス
SERVICE_STAFF_NOT_FOUND = "スタッフ {staff_id} が見つかりません"
SERVICE_REQUEST_NOT_FOUND = "申請 {request_id} が見つかりません"
SERVICE_REVIEWER_NOT_FOUND = "レビュワースタッフ {reviewer_id} が見つかりません"
SERVICE_ROLE_ALREADY_ASSIGNED = "スタッフは既に要求された権限を持っています"
SERVICE_NO_APPROVAL_PERMISSION = "この申請を承認する権限がありません"

# 承認申請サービス
SERVICE_UNSUPPORTED_RESOURCE_TYPE = "サポートされていないリソースタイプです: {resource_type}"
SERVICE_RESOURCE_ID_REQUIRED_FOR_UPDATE = "更新操作にはresource_idが必要です"
SERVICE_RECIPIENT_NOT_FOUND = "利用者 {recipient_id} が見つかりません"
SERVICE_RESOURCE_ID_REQUIRED_FOR_DELETE = "削除操作にはresource_idまたはwelfare_recipient_idが必要です"
SERVICE_UNSUPPORTED_ACTION_TYPE = "サポートされていないアクションタイプです: {action_type}"
SERVICE_EMPLOYEE_ACTION_REQUEST_NOT_FOUND = "承認申請 {request_id} が見つかりません"

# カレンダーサービス
SERVICE_CALENDAR_ALREADY_EXISTS = "事業所 {office_id} は既にカレンダーアカウントを持っています"
SERVICE_CALENDAR_NOT_FOUND = "カレンダーアカウント {account_id} が見つかりません"
SERVICE_CLIENT_EMAIL_NOT_FOUND = "設定ファイルにメールアドレス情報が見つかりません"
SERVICE_INVALID_JSON = "設定ファイルの形式が正しくありません: {error}"
SERVICE_ACCOUNT_KEY_NOT_FOUND = "カレンダー連携用の設定情報が見つかりません"

# ==========================================
# 申請関連（Employee Action / Role Change共通）
# ==========================================

REQUEST_NOT_FOUND = "申請が見つかりません"
REQUEST_ALREADY_PROCESSED = "申請は既に{status}です"
REQUEST_OFFICE_MISMATCH = "自分の事業所の申請のみ操作できます"
REQUEST_DELETE_OWN_ONLY = "自分の申請のみ削除できます"
REQUEST_CANNOT_DELETE_PROCESSED = "{status}状態の申請は削除できません"

# ==========================================
# アセスメント関連 (assessment.py)
# ==========================================

ASSESSMENT_FAMILY_MEMBER_NOT_FOUND = "家族メンバーが見つかりません"
ASSESSMENT_SERVICE_HISTORY_NOT_FOUND = "サービス利用歴が見つかりません"
ASSESSMENT_HOSPITAL_VISIT_NOT_FOUND = "通院歴が見つかりません"

# ==========================================
# 通知関連 (notices.py)
# ==========================================

NOTICE_NOT_FOUND = "通知が見つかりません"
NOTICE_READ_OWN_ONLY = "自分の通知のみ既読にできます"
NOTICE_DELETE_OWN_ONLY = "自分の通知のみ削除できます"

# ==========================================
# スタッフ関連 (staffs.py)
# ==========================================

STAFF_NOT_FOUND = "スタッフが見つかりません"
STAFF_NAME_UPDATE_FAILED = "名前の更新に失敗しました"
STAFF_PASSWORD_CHANGE_FAILED = "パスワードの変更に失敗しました"
STAFF_PASSWORD_MISMATCH = "新しいパスワードが一致しません"
STAFF_CURRENT_PASSWORD_INCORRECT = "現在のパスワードが正しくありません"
STAFF_PASSWORD_CONTAINS_EMAIL = "パスワードにメールアドレスの一部を含めることはできません"
STAFF_PASSWORD_CONTAINS_NAME = "パスワードに名前を含めることはできません"
STAFF_EMAIL_CHANGE_REQUEST_FAILED = "メールアドレス変更申請に失敗しました"
STAFF_EMAIL_CHANGE_VERIFY_FAILED = "メールアドレス変更の確認に失敗しました"

# ==========================================
# カレンダー関連 (calendar.py)
# ==========================================

CALENDAR_OWNER_ONLY = "この操作を行う権限がありません。カレンダー設定はowner権限が必要です。"
CALENDAR_UPDATE_OWNER_ONLY = "この操作を行う権限がありません。カレンダー設定の更新はowner権限が必要です。"
CALENDAR_DELETE_OWNER_ONLY = "この操作を行う権限がありません。カレンダー連携の解除はowner権限が必要です。"
CALENDAR_NOT_FOUND_FOR_OFFICE = "事業所のカレンダー設定が見つかりません。"
CALENDAR_ACCOUNT_NOT_FOUND = "カレンダーアカウントが見つかりません。"
CALENDAR_SETUP_ERROR = "カレンダー連携設定中に予期しないエラーが発生しました"
CALENDAR_UPDATE_FAILED = "カレンダー設定の更新に失敗しました"
CALENDAR_UPDATE_ERROR = "カレンダー設定の更新中に予期しないエラーが発生しました"
CALENDAR_DELETE_ERROR = "カレンダー連携の解除中にエラーが発生しました"
CALENDAR_SYNC_ERROR = "イベント同期中にエラーが発生しました"
CALENDAR_SETUP_SUCCESS_WITH_CONNECTION = "カレンダー連携設定が正常に完了し、接続テストに成功しました。"
CALENDAR_SETUP_FAILED_CONNECTION = "カレンダー連携設定は完了しましたが、接続テストに失敗しました。設定を確認してください。"
CALENDAR_ALREADY_EXISTS = "この事業所は既にカレンダー連携設定が存在します。"
CALENDAR_SETUP_FAILED = "カレンダー連携設定に失敗しました。"
CALENDAR_UPDATE_SUCCESS_WITH_CONNECTION = "カレンダー設定を更新し、接続テストに成功しました。"
CALENDAR_UPDATE_FAILED_CONNECTION = "カレンダー設定は更新されましたが、接続テストに失敗しました。設定を確認してください。"
CALENDAR_DELETE_SUCCESS = "カレンダー連携を解除しました。"
CALENDAR_SYNC_SUCCESS = "{synced}件のイベントを同期しました。{failed}件が失敗しました。"

# ==========================================
# ダッシュボード関連 (dashboard.py)
# ==========================================

DASHBOARD_OFFICE_NOT_FOUND = "事業所情報が見つかりません"

# ==========================================
# 個別支援計画状態関連 (support_plan_statuses.py)
# ==========================================

SUPPORT_PLAN_STATUS_NOT_FOUND = "状態ID {status_id} が見つかりません。"
SUPPORT_PLAN_NO_ACCESS = "この状態にアクセスする権限がありません。"

# ==========================================
# 個別支援計画関連 (support_plans.py)
# ==========================================

SUPPORT_PLAN_RECIPIENT_NOT_FOUND = "利用者ID {recipient_id} が見つかりません。"
SUPPORT_PLAN_NO_PERMISSION = "この利用者の個別支援計画にアクセスする権限がありません。"
SUPPORT_PLAN_CYCLE_NOT_FOUND = "計画サイクルID {cycle_id} が見つかりません。"
SUPPORT_PLAN_DELIVERABLE_NOT_FOUND = "成果物ID {deliverable_id} が見つかりません。"
SUPPORT_PLAN_NO_DELIVERABLE_ACCESS = "この成果物にアクセスする権限がありません。"
SUPPORT_PLAN_NO_DELIVERABLE_UPDATE_ACCESS = "この成果物を更新する権限がありません。"
SUPPORT_PLAN_NO_DELIVERABLE_DELETE_ACCESS = "この成果物を削除する権限がありません。"
SUPPORT_PLAN_EMPLOYEE_CANNOT_UPLOAD = "一般スタッフは個別支援計画のPDFを登録できません。管理者または事業所管理者に依頼してください。"
SUPPORT_PLAN_EMPLOYEE_CANNOT_DELETE = "一般スタッフは個別支援計画のPDFを削除できません。管理者または事業所管理者に依頼してください。"
SUPPORT_PLAN_NO_CYCLE_ACCESS = "このサイクルにアクセスする権限がありません。"
SUPPORT_PLAN_NO_OFFICE_PDF_ACCESS = "この事業所のPDFにアクセスする権限がありません"

# ==========================================
# 福祉受給者関連 (welfare_recipients.py)
# ==========================================

RECIPIENT_CATEGORY_MISSING = "障害詳細のカテゴリが未指定です。"
RECIPIENT_MUST_HAVE_OFFICE = "スタッフは事業所に所属している必要があります"
RECIPIENT_NOT_FOUND = "利用者が見つかりません"
RECIPIENT_ACCESS_DENIED = "この利用者にアクセスする権限がありません"
RECIPIENT_UPDATE_NOT_FOUND = "利用者の更新に失敗しました"
RECIPIENT_DELETED_SUCCESS = "利用者を削除しました"
RECIPIENT_REPAIR_PERMISSION_DENIED = "管理者または事業所管理者のみが個別支援計画の修復を実行できます"
RECIPIENT_CREATE_SUCCESS = "利用者の登録が完了しました"
RECIPIENT_REPAIR_SUPPORT_PLAN_SUCCESS = "個別支援計画が正常に修復されました"

# ==========================================
# 承認申請共通メッセージ
# ==========================================

EMPLOYEE_REQUEST_PENDING = "申請を作成しました。承認待ちです"

# ==========================================
# 利用規約・プライバシーポリシー同意関連 (terms.py)
# ==========================================

# 同意履歴の取得
TERMS_AGREEMENT_NOT_FOUND = "同意履歴が見つかりません"
TERMS_AGREEMENT_ALREADY_EXISTS = "既に同意履歴が存在します"

# 同意処理
TERMS_BOTH_REQUIRED = "利用規約とプライバシーポリシーの両方に同意する必要があります"
TERMS_AGREEMENT_SUCCESS = "利用規約とプライバシーポリシーへの同意が記録されました"
TERMS_AGREEMENT_UPDATED = "同意情報を更新しました"

# バージョンチェック
TERMS_VERSION_REQUIRED = "利用規約のバージョンが指定されていません"
PRIVACY_VERSION_REQUIRED = "プライバシーポリシーのバージョンが指定されていません"
TERMS_AGREEMENT_OUTDATED = "利用規約が更新されました。最新版への同意が必要です"
PRIVACY_AGREEMENT_OUTDATED = "プライバシーポリシーが更新されました。最新版への同意が必要です"
TERMS_AGREEMENT_REQUIRED = "サービスを利用するには利用規約への同意が必要です"

# 権限関連
TERMS_ACCESS_DENIED = "この同意履歴にアクセスする権限がありません"
TERMS_UPDATE_DENIED = "この同意履歴を更新する権限がありません"

# スタッフ関連
TERMS_STAFF_NOT_FOUND = "スタッフ {staff_id} が見つかりません"
TERMS_STAFF_REQUIRED = "スタッフIDが必要です"

# ==========================================
# 退会申請関連 (withdrawal_requests.py)
# ==========================================

# 申請作成
WITHDRAWAL_OWNER_ONLY = "退会申請は事業所管理者のみ作成できます"
WITHDRAWAL_TITLE_REQUIRED = "タイトルを入力してください"
WITHDRAWAL_REASON_REQUIRED = "申請内容を入力してください"
WITHDRAWAL_NO_OFFICE = "事業所に所属していません"

# 申請取得
WITHDRAWAL_LIST_OWNER_OR_ADMIN_ONLY = "退会申請一覧は事業所管理者またはアプリ管理者のみ取得できます"

# 承認/却下
WITHDRAWAL_APPROVE_APP_ADMIN_ONLY = "退会申請を承認する権限がありません"
WITHDRAWAL_REJECT_APP_ADMIN_ONLY = "退会申請を却下する権限がありません"
WITHDRAWAL_REQUEST_NOT_FOUND = "退会申請が見つかりません"
WITHDRAWAL_ALREADY_PROCESSED = "この申請は既に{status}です"

# 成功メッセージ
WITHDRAWAL_REQUEST_CREATED = "退会申請を作成しました"
WITHDRAWAL_REQUEST_APPROVED = "退会申請を承認しました"
WITHDRAWAL_REQUEST_REJECTED = "退会申請を却下しました"

# ==========================================
# 課金関連 (billing.py)
# ==========================================

# 課金状態取得
BILLING_OFFICE_NOT_FOUND = "所属する事務所が見つかりません"
BILLING_INFO_NOT_FOUND = "課金情報が見つかりません"

# Stripe Checkout/Portal
BILLING_STRIPE_NOT_CONFIGURED = "支払い連携が設定されていません"
BILLING_STRIPE_CUSTOMER_NOT_FOUND = "支払い情報が見つかりません。先に支払い方法を登録してください。"
BILLING_CHECKOUT_SESSION_FAILED = "支払い画面の表示に失敗しました"
BILLING_PORTAL_SESSION_FAILED = "支払い方法の管理画面の表示に失敗しました"

# Webhook
BILLING_WEBHOOK_SECRET_NOT_SET = "決済通知の確認設定が不足しています"
BILLING_WEBHOOK_INVALID_PAYLOAD = "決済通知の内容を確認できません"
BILLING_WEBHOOK_INVALID_SIGNATURE = "決済通知の確認に失敗しました"
BILLING_WEBHOOK_PROCESSING_FAILED = "決済通知の処理に失敗しました"
BILLING_WEBHOOK_EVENT_DUPLICATE = "このイベントは既に処理済みです"

# 課金制限（deps.py）
BILLING_PAYMENT_REQUIRED = "無料お試し期間が終了しました。引き続き機能をご利用いただくには課金が必要です。"
