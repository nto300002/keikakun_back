from fastapi import APIRouter

from app.api.v1.endpoints import (
    auths,
    mfa,
    offices,
    staffs,
    office_staff,
    dashboard,
    welfare_recipients,
    support_plans,
    support_plan_statuses,
    calendar,
    assessment,
    role_change_requests,
    notices,
    messages,
    employee_action_requests,
    terms,
    csrf,
    withdrawal_requests,
    admin_offices,
    admin_audit_logs,
    admin_inquiries,
    admin_announcements,
    archived_staffs,
    inquiries,
    billing,
)

api_router = APIRouter()

# Include routers from endpoints
api_router.include_router(csrf.router, tags=["csrf"])
api_router.include_router(auths.router, prefix="/auth", tags=["auth"])
api_router.include_router(staffs.router, prefix="/staffs", tags=["staffs"])
api_router.include_router(offices.router, prefix="/offices", tags=["offices"])
api_router.include_router(office_staff.router, prefix="/staff", tags=["staff-office"])
api_router.include_router(mfa.router, prefix="/auth", tags=["mfa"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(welfare_recipients.router, prefix="/welfare-recipients", tags=["welfare-recipients"])
api_router.include_router(support_plans.router, prefix="/support-plans", tags=["support-plans"])
api_router.include_router(support_plan_statuses.router, prefix="/support-plan-statuses", tags=["support-plan-statuses"])
api_router.include_router(calendar.router, prefix="/calendar", tags=["calendar"])
api_router.include_router(assessment.router, tags=["assessment"])
api_router.include_router(role_change_requests.router, prefix="/role-change-requests", tags=["role-change-requests"])
api_router.include_router(notices.router, prefix="/notices", tags=["notices"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(employee_action_requests.router, prefix="/employee-action-requests", tags=["employee-action-requests"])
api_router.include_router(terms.router, prefix="/terms", tags=["terms"])
api_router.include_router(withdrawal_requests.router, prefix="/withdrawal-requests", tags=["withdrawal-requests"])
api_router.include_router(admin_offices.router, prefix="/admin/offices", tags=["admin-offices"])
api_router.include_router(admin_audit_logs.router, prefix="/admin/audit-logs", tags=["admin-audit-logs"])
api_router.include_router(admin_inquiries.router, prefix="/admin/inquiries", tags=["admin-inquiries"])
api_router.include_router(admin_announcements.router, prefix="/admin/announcements", tags=["admin-announcements"])
api_router.include_router(archived_staffs.router, prefix="/admin/archived-staffs", tags=["admin-archived-staffs"])
api_router.include_router(inquiries.router, prefix="/inquiries", tags=["inquiries"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
