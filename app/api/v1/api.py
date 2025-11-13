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
    employee_action_requests,
)

api_router = APIRouter()

# Include routers from endpoints
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
api_router.include_router(employee_action_requests.router, prefix="/employee-action-requests", tags=["employee-action-requests"])
