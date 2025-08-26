import enum

class StaffRole(str, enum.Enum):
    employee = 'employee'
    manager = 'manager'
    owner = 'owner'

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
    free = 'free'          # 無料プラン
    active = 'active'        # 課金中
    past_due = 'past_due'    # 支払い延滞
    canceled = 'canceled'    # キャンセル済み