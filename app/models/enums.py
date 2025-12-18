import enum

class StaffRole(str, enum.Enum):
    employee = 'employee'
    manager = 'manager'
    owner = 'owner'
    app_admin = 'app_admin'  # アプリ管理者（退会承認、全体お知らせ送信等）

class OfficeType(str, enum.Enum):
    transition_to_employment = 'transition_to_employment'
    type_B_office = 'type_B_office'
    type_A_office = 'type_A_office'

class GenderType(str, enum.Enum):
    male = 'male'
    female = 'female'
    other = 'other'

class SupportPlanStep(str, enum.Enum):
    assessment = 'assessment'
    draft_plan = 'draft_plan'
    staff_meeting = 'staff_meeting'
    final_plan_signed = 'final_plan_signed'
    monitoring = 'monitoring'

class DeliverableType(str, enum.Enum):
    assessment_sheet = 'assessment_sheet'
    draft_plan_pdf = 'draft_plan_pdf'
    staff_meeting_minutes = 'staff_meeting_minutes'
    final_plan_signed_pdf = 'final_plan_signed_pdf'
    monitoring_report_pdf = 'monitoring_report_pdf'

class AssessmentSheetType(str, enum.Enum):
    """アセスメントシートの種類"""
    basic_info = '1-1.基本情報'
    employment_info = '1-2.就労関係'
    issue_analysis = '2.課題分析'

class BillingStatus(str, enum.Enum):
    free = 'free'                    # 無料トライアル
    early_payment = 'early_payment'  # 早期支払い完了（無料期間中に課金設定済み）
    active = 'active'                # 課金中
    past_due = 'past_due'            # 支払い遅延
    canceling = 'canceling'          # キャンセル予定（期間終了時にキャンセル）
    canceled = 'canceled'            # キャンセル済み

class FormOfResidence(str, enum.Enum):
    """居住形態"""
    home_with_family = "home_with_family"
    home_alone = "home_alone"
    group_home = "group_home"
    institution = "institution"
    hospital = "hospital"
    other = "other"

class MeansOfTransportation(str, enum.Enum):
    """交通手段"""
    walk = "walk"
    bicycle = "bicycle"
    motorbike = "motorbike"
    car_self = "car_self"
    car_transport = "car_transport"
    public_transport = "public_transport"
    welfare_transport = "welfare_transport"
    other = "other"

class LivelihoodProtection(str, enum.Enum):
    """生活保護受給状況"""
    not_receiving = "not_receiving"
    receiving_with_allowance = "receiving_with_allowance"
    receiving_without_allowance = "receiving_without_allowance"
    applying = "applying"
    planning = "planning"

class ApplicationStatus(str, enum.Enum):
    """手帳・制度の申請・取得状況"""
    acquired = "acquired"
    applying = "applying"
    planning = "planning"
    not_applicable = "not_applicable"

class PhysicalDisabilityGrade(str, enum.Enum):
    """身体障害者手帳の等級"""
    grade_1 = "1"
    grade_2 = "2"
    grade_3 = "3"
    grade_4 = "4"
    grade_5 = "5"
    grade_6 = "6"

class PhysicalDisabilityType(str, enum.Enum):
    """身体障害の種別"""
    visual = "visual"
    hearing = "hearing"
    limb = "limb"
    internal = "internal"
    other = "other"

class IntellectualDisabilityGrade(str, enum.Enum):
    """療育手帳の等級区分"""
    a = "A"
    b = "B"

class MentalHealthDisabilityGrade(str, enum.Enum):
    """精神障害者保健福祉手帳の等級"""
    grade_1 = "1"
    grade_2 = "2"
    grade_3 = "3"

class DisabilityBasicPensionGrade(str, enum.Enum):
    """障害基礎年金の等級"""
    grade_1 = "1"
    grade_2 = "2"

class OtherDisabilityPensionGrade(str, enum.Enum):
    """その他の障害年金等級"""
    grade_1 = "1"
    grade_2 = "2"
    grade_3 = "3"

class PublicAssistanceStatus(str, enum.Enum):
    """生活保護の受給状況"""
    receiving_with_care_allowance = "receiving_with_care"
    receiving_without_care_allowance = "receiving_without_care"
    not_receiving = "not_receiving"

class DisabilityCategory(str, enum.Enum):
    """障害・制度のカテゴリ"""
    physical_handbook = "physical_handbook"
    intellectual_handbook = "intellectual_handbook"
    mental_health_handbook = "mental_health_handbook"
    disability_basic_pension = "disability_basic_pension"
    other_disability_pension = "other_disability_pension"
    public_assistance = "public_assistance"

class CalendarConnectionStatus(str, enum.Enum):
    """カレンダー連携状態"""
    not_connected = "not_connected"  # 未連携
    connected = "connected"          # 連携済み
    error = "error"                  # エラー状態
    suspended = "suspended"          # 一時停止

class NotificationTiming(str, enum.Enum):
    """通知タイミング設定"""
    early = "early"        # 早め (30日前、14日前、7日前、3日前、1日前)
    standard = "standard"  # 標準 (30日前、7日前、1日前)
    minimal = "minimal"    # 最小限 (7日前、1日前)
    custom = "custom"      # カスタム

class CalendarEventType(str, enum.Enum):
    """カレンダーイベントタイプ"""
    renewal_deadline = "renewal_deadline"       # 更新期限
    monitoring_deadline = "monitoring_deadline" # モニタリング期限
    custom = "custom"                           # カスタムイベント

class CalendarSyncStatus(str, enum.Enum):
    """カレンダー同期ステータス"""
    pending = "pending"     # 同期待ち
    synced = "synced"       # 同期済み
    failed = "failed"       # 同期失敗
    cancelled = "cancelled" # キャンセル済み

class ReminderPatternType(str, enum.Enum):
    """リマインダーパターンタイプ"""
    single = "single"               # 単発イベント
    multiple_fixed = "multiple_fixed" # 固定日程の複数イベント
    recurring_rule = "recurring_rule" # RRULEによる繰り返し

class EventInstanceStatus(str, enum.Enum):
    """イベントインスタンスステータス"""
    pending = "pending"       # 作成予定
    created = "created"       # 作成済み
    modified = "modified"     # 変更済み
    cancelled = "cancelled"   # キャンセル済み
    completed = "completed"   # 完了

class Household(str, enum.Enum):
    """世帯区分"""
    same = "same"           # 同じ
    separate = "separate"   # 別

class MedicalCareInsurance(str, enum.Enum):
    """医療保険の種類"""
    national_health_insurance = "national_health_insurance"  # 国保
    mutual_aid = "mutual_aid"                                # 共済
    social_insurance = "social_insurance"                    # 社保
    livelihood_protection = "livelihood_protection"          # 生活保護
    other = "other"                                          # その他

class AidingType(str, enum.Enum):
    """公費負担の種類"""
    none = "none"                # なし
    subsidized = "subsidized"    # あり（一部補助）
    full_exemption = "full_exemption"  # 全額免除

class WorkConditions(str, enum.Enum):
    """就労状況"""
    general_employment = "general_employment"              # 一般就労
    part_time = "part_time"                                # パート、アルバイト
    transition_support = "transition_support"              # 就労移行支援
    continuous_support_a = "continuous_support_a"          # 就労継続支援A
    continuous_support_b = "continuous_support_b"          # 就労継続支援B
    main_employment = "main_employment"                    # 本就労
    other = "other"                                        # その他

class WorkOutsideFacility(str, enum.Enum):
    """施設外就労の希望"""
    hope = "hope"              # 希望する
    not_hope = "not_hope"      # 希望しない
    undecided = "undecided"    # 未定

class RequestStatus(str, enum.Enum):
    """リクエストステータス"""
    pending = 'pending'      # 承認待ち
    approved = 'approved'    # 承認済み
    rejected = 'rejected'    # 却下

class NoticeType(str, enum.Enum):
    """通知タイプ"""
    # Role変更リクエスト（承認者向け）
    role_change_pending = 'role_change_pending'  # 承認待ちのRole変更リクエスト
    role_change_approved = 'role_change_approved'
    role_change_rejected = 'role_change_rejected'

    # Role変更リクエスト（送信者向け）
    role_change_request_sent = 'role_change_request_sent'  # リクエスト送信完了通知

    # Employee制限リクエスト（承認者向け）
    employee_action_pending = 'employee_action_pending'  # 承認待ちのEmployee制限リクエスト
    employee_action_approved = 'employee_action_approved'
    employee_action_rejected = 'employee_action_rejected'

    # Employee制限リクエスト（送信者向け）
    employee_action_request_sent = 'employee_action_request_sent'  # リクエスト送信完了通知

class ActionType(str, enum.Enum):
    """アクションタイプ"""
    create = 'create'
    update = 'update'
    delete = 'delete'

class ResourceType(str, enum.Enum):
    """リソースタイプ"""
    welfare_recipient = 'welfare_recipient'
    support_plan_cycle = 'support_plan_cycle'
    support_plan_status = 'support_plan_status'

class MessageType(str, enum.Enum):
    """メッセージタイプ"""
    personal = 'personal'           # 個別メッセージ
    announcement = 'announcement'   # 一斉通知（お知らせ）
    system = 'system'               # システム通知
    inquiry = 'inquiry'             # 問い合わせ
    inquiry_reply = 'inquiry_reply' # 問い合わせ返信

class MessagePriority(str, enum.Enum):
    """メッセージ優先度"""
    low = 'low'           # 低
    normal = 'normal'     # 通常
    high = 'high'         # 高
    urgent = 'urgent'     # 緊急


class ApprovalResourceType(str, enum.Enum):
    """承認リクエストのリソースタイプ"""
    role_change = 'role_change'           # ロール変更
    employee_action = 'employee_action'   # 従業員制限
    withdrawal = 'withdrawal'             # 退会


class AuditLogTargetType(str, enum.Enum):
    """監査ログの対象リソースタイプ"""
    staff = 'staff'                           # スタッフ関連操作
    office = 'office'                         # 事務所関連操作
    withdrawal_request = 'withdrawal_request' # 退会リクエスト関連操作
    terms_agreement = 'terms_agreement'       # 利用規約同意記録


class InquiryStatus(str, enum.Enum):
    """問い合わせステータス"""
    new = 'new'                 # 新規受付（未確認）
    open = 'open'               # 確認済み（対応中）
    in_progress = 'in_progress' # 担当者割当済み
    answered = 'answered'       # 回答済み
    closed = 'closed'           # クローズ済み
    spam = 'spam'               # スパム判定


class InquiryPriority(str, enum.Enum):
    """問い合わせ優先度"""
    low = 'low'        # 低
    normal = 'normal'  # 通常
    high = 'high'      # 高
