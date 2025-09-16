from fastapi import APIRouter

from app.api.v1.endpoints import auths, mfa, offices, staffs, office_staff, dashboard

api_router = APIRouter()

# Include routers from endpoints
api_router.include_router(auths.router, prefix="/auth", tags=["auth"])
api_router.include_router(staffs.router, prefix="/staffs", tags=["staffs"])
api_router.include_router(offices.router, prefix="/offices", tags=["offices"])
api_router.include_router(office_staff.router, prefix="/staff", tags=["staff-office"])
api_router.include_router(mfa.router, prefix="/auth", tags=["mfa"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
