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

# トークンリフレッシュ
AUTH_INVALID_REFRESH_TOKEN = "リフレッシュトークンが無効です"
AUTH_REFRESH_TOKEN_BLACKLISTED = "このリフレッシュトークンは無効化されています。再度ログインしてください。"
AUTH_TOKEN_REFRESHED = "トークンを更新しました"

# MFA検証（ログイン時）
AUTH_INVALID_TEMPORARY_TOKEN = "一時トークンが無効または期限切れです"
AUTH_MFA_NOT_CONFIGURED = "多要素認証が正しく設定されていません"
AUTH_INVALID_MFA_CODE = "認証コードまたはリカバリコードが正しくありません"
AUTH_MFA_VERIFICATION_SUCCESS = "多要素認証に成功しました"

# ログアウト
AUTH_LOGOUT_SUCCESS = "ログアウトしました"

# パスワードリセット
AUTH_PASSWORD_RESET_EMAIL_SENT = "パスワードリセット用のメールを送信しました。メールをご確認ください。"
AUTH_RESET_TOKEN_VALID = "トークンは有効です"
AUTH_RESET_TOKEN_INVALID_OR_EXPIRED = "トークンが無効または期限切れです。新しいリセットリンクをリクエストしてください。"
AUTH_RESET_TOKEN_ALREADY_USED = "このトークンは既に使用されています。新しいリセットリンクをリクエストしてください。"
AUTH_PASSWORD_RESET_SUCCESS = "パスワードが正常にリセットされました。新しいパスワードでログインしてください。"
AUTH_PASSWORD_RESET_FAILED = "パスワードリセットに失敗しました。時間をおいて再度お試しください。"
AUTH_PASSWORD_BREACHED = "このパスワードは過去のデータ侵害で流出しています。別のパスワードを選択してください。"
AUTH_TOKEN_INVALIDATED_BY_PASSWORD_CHANGE = "パスワードが変更されたため、このトークンは無効化されました。再度ログインしてください。"

# レート制限
AUTH_RATE_LIMIT_EXCEEDED = "リクエスト回数が多すぎます。しばらくしてから再度お試しください。"

# ==========================================
# 権限関連 (deps.py)
# ==========================================

PERM_CREDENTIALS_INVALID = "認証情報を検証できません"
PERM_MANAGER_OR_OWNER_REQUIRED = "管理者または事業所管理者の権限が必要です"
PERM_OWNER_REQUIRED = "事業所管理者の権限が必要です"
PERM_OFFICE_REQUIRED = "スタッフは事業所に所属している必要があります"
PERM_OPERATION_FORBIDDEN = "この操作を行う権限がありません。"
PERM_OPERATION_FORBIDDEN_GENERIC = "この操作を実行する権限がありません"
PERM_MANAGER_OR_OWNER_APPROVE = "managerまたはownerのみがリクエストを承認できます"
PERM_MANAGER_OR_OWNER_REJECT = "managerまたはownerのみがリクエストを却下できます"

# ==========================================
# MFA（多要素認証）関連 (mfa.py)
# ==========================================

MFA_ALREADY_ENABLED = "多要素認証は既に有効になっています"
MFA_NOT_ENROLLED = "多要素認証が登録されていません"
MFA_INVALID_CODE = "認証コードが正しくありません"
MFA_VERIFICATION_SUCCESS = "多要素認証の検証に成功しました"
MFA_NOT_ENABLED = "多要素認証は有効になっていません"
MFA_INCORRECT_PASSWORD = "パスワードが正しくありません"
MFA_DISABLED_SUCCESS = "多要素認証を無効にしました"
MFA_ENABLED_SUCCESS = "多要素認証を有効にしました"

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
RECIPIENT_REPAIR_PERMISSION_DENIED = "managerまたはownerのみが個別支援計画の修復を実行できます"

# ==========================================
# ロール変更リクエスト (role_change_requests.py)
# ==========================================

ROLE_ALREADY_ASSIGNED = "既に{role}の権限を持っています"
ROLE_NO_OFFICE = "事業所に所属していません"
ROLE_REQUEST_NOT_FOUND = "リクエストが見つかりません"
ROLE_REQUEST_ALREADY_PROCESSED = "リクエストは既に{status}です"
ROLE_NO_PERMISSION_TO_APPROVE = "このリクエストを承認する権限がありません"
ROLE_NO_PERMISSION_TO_REJECT = "このリクエストを却下する権限がありません"
ROLE_CAN_ONLY_DELETE_OWN = "自分のリクエストのみ削除できます"
ROLE_CANNOT_DELETE_PROCESSED = "{status}状態のリクエストは削除できません"

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
SUPPORT_PLAN_MONITORING_ONLY = "モニタリング期限はモニタリングステータスのみ設定できます。"
SUPPORT_PLAN_STATUS_NOT_FOUND = "ステータスID {status_id} が見つかりません。"
SUPPORT_PLAN_NO_ACCESS = "このステータスにアクセスする権限がありません。"
SUPPORT_PLAN_RECIPIENT_NOT_FOUND = "利用者ID {recipient_id} が見つかりません。"
SUPPORT_PLAN_NO_PERMISSION = "この利用者の個別支援計画にアクセスする権限がありません。"
SUPPORT_PLAN_CYCLE_NOT_FOUND = "計画サイクルID {cycle_id} が見つかりません。"
SUPPORT_PLAN_DELIVERABLE_NOT_FOUND = "成果物ID {deliverable_id} が見つかりません。"
SUPPORT_PLAN_NO_DELIVERABLE_ACCESS = "この成果物にアクセスする権限がありません。"
SUPPORT_PLAN_NO_DELIVERABLE_UPDATE_ACCESS = "この成果物を更新する権限がありません。"
SUPPORT_PLAN_NO_DELIVERABLE_DELETE_ACCESS = "この成果物を削除する権限がありません。"
SUPPORT_PLAN_EMPLOYEE_CANNOT_UPLOAD = "Employee権限では個別支援計画のPDFをアップロードできません。Manager/Owner権限のスタッフにアップロードを依頼してください。"
SUPPORT_PLAN_EMPLOYEE_CANNOT_DELETE = "Employee権限では個別支援計画のPDFを削除できません。Manager/Owner権限のスタッフに削除を依頼してください。"
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

EXC_BAD_REQUEST = "不正なリクエストです"
EXC_NOT_FOUND = "見つかりません"
EXC_FORBIDDEN = "アクセスが拒否されました"
EXC_INTERNAL_ERROR = "サーバー内部エラーが発生しました"

# ==========================================
# バリデーション (schemas)
# ==========================================

# スタッフスキーマ
VALIDATION_CANNOT_REGISTER_AS_OWNER = "このエンドポイントからオーナーとして登録できません"
VALIDATION_NAME_CANNOT_BE_EMPTY = "{field_name}は空にできません"
VALIDATION_NAME_TOO_LONG = "{field_name}は50文字以内にしてください"
VALIDATION_NAME_CANNOT_BE_ONLY_NUMBERS = "名前に数字のみは使用できません"
VALIDATION_NAME_INVALID_CHARACTERS = "名前に使用できない文字が含まれています（日本語のみ使用可能）"
VALIDATION_PASSWORD_TOO_SHORT = "パスワードは8文字以上である必要があります"
VALIDATION_PASSWORD_COMPLEXITY = "パスワードは次のうち少なくとも3つを含む必要があります: 英字小文字、大文字、数字、記号"

# カレンダーアカウント
VALIDATION_REMINDER_DAYS_POSITIVE = "リマインダー日数は正の整数である必要があります"
VALIDATION_CUSTOM_REMINDER_FORMAT = "カスタムリマインダー日数はカンマ区切りの正の整数である必要があります"
VALIDATION_MISSING_FIELD_IN_JSON = "サービスアカウントJSONに必須フィールドがありません: {field}"
VALIDATION_INVALID_SERVICE_ACCOUNT_TYPE = "無効なサービスアカウントJSONです: typeは'service_account'である必要があります"
VALIDATION_INVALID_JSON_FORMAT = "無効なJSON形式です: {error}"

# 福祉受給者
VALIDATION_BIRTH_DATE_FUTURE = "生年月日は未来の日付にできません"

# ダッシュボード
VALIDATION_ID_MUST_BE_UUID = "idは有効なUUIDである必要があります"

# ==========================================
# サービス層
# ==========================================

# ロール変更サービス
SERVICE_STAFF_NOT_FOUND = "スタッフ {staff_id} が見つかりません"
SERVICE_REQUEST_NOT_FOUND = "リクエスト {request_id} が見つかりません"
SERVICE_REVIEWER_NOT_FOUND = "レビュワースタッフ {reviewer_id} が見つかりません"
SERVICE_ROLE_ALREADY_ASSIGNED = "スタッフは既に要求された権限を持っています"
SERVICE_NO_APPROVAL_PERMISSION = "このリクエストを承認する権限がありません"

# Employee制限サービス
SERVICE_UNSUPPORTED_RESOURCE_TYPE = "サポートされていないリソースタイプです: {resource_type}"
SERVICE_RESOURCE_ID_REQUIRED_FOR_UPDATE = "更新操作にはresource_idが必要です"
SERVICE_RECIPIENT_NOT_FOUND = "利用者 {recipient_id} が見つかりません"
SERVICE_RESOURCE_ID_REQUIRED_FOR_DELETE = "削除操作にはresource_idまたはwelfare_recipient_idが必要です"
SERVICE_UNSUPPORTED_ACTION_TYPE = "サポートされていないアクションタイプです: {action_type}"
SERVICE_EMPLOYEE_ACTION_REQUEST_NOT_FOUND = "Employee制限リクエスト {request_id} が見つかりません"

# カレンダーサービス
SERVICE_CALENDAR_ALREADY_EXISTS = "事業所 {office_id} は既にカレンダーアカウントを持っています"
SERVICE_CALENDAR_NOT_FOUND = "カレンダーアカウント {account_id} が見つかりません"
SERVICE_CLIENT_EMAIL_NOT_FOUND = "サービスアカウントJSONにclient_emailが見つかりません"
SERVICE_INVALID_JSON = "無効なJSON形式です: {error}"
SERVICE_ACCOUNT_KEY_NOT_FOUND = "サービスアカウントキーが見つかりません"

# ==========================================
# リクエスト関連（Employee Action / Role Change共通）
# ==========================================

REQUEST_NOT_FOUND = "リクエストが見つかりません"
REQUEST_ALREADY_PROCESSED = "リクエストは既に{status}です"
REQUEST_OFFICE_MISMATCH = "自分の事業所のリクエストのみ操作できます"
REQUEST_DELETE_OWN_ONLY = "自分のリクエストのみ削除できます"
REQUEST_CANNOT_DELETE_PROCESSED = "{status}状態のリクエストは削除できません"

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
STAFF_EMAIL_CHANGE_REQUEST_FAILED = "メールアドレス変更リクエストに失敗しました"
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
# 個別支援計画ステータス関連 (support_plan_statuses.py)
# ==========================================

SUPPORT_PLAN_STATUS_NOT_FOUND = "ステータスID {status_id} が見つかりません。"
SUPPORT_PLAN_NO_ACCESS = "このステータスにアクセスする権限がありません。"

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
SUPPORT_PLAN_EMPLOYEE_CANNOT_UPLOAD = "Employee権限では個別支援計画のPDFをアップロードできません。Manager/Owner権限のスタッフにアップロードを依頼してください。"
SUPPORT_PLAN_EMPLOYEE_CANNOT_DELETE = "Employee権限では個別支援計画のPDFを削除できません。Manager/Owner権限のスタッフに削除を依頼してください。"
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
RECIPIENT_REPAIR_PERMISSION_DENIED = "managerまたはownerのみが個別支援計画の修復を実行できます"
RECIPIENT_CREATE_SUCCESS = "利用者の登録が完了しました"
RECIPIENT_REPAIR_SUPPORT_PLAN_SUCCESS = "個別支援計画が正常に修復されました"

# ==========================================
# Employee制限リクエスト共通メッセージ
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
