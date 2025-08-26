import enum

class StaffRole(str, enum.Enum):
    service_administrator = "service_administrator"
    general_staff = "general_staff"

class OfficeType(str, enum.Enum):
    main_office = "main_office"
    satellite_office = "satellite_office"

class BillingStatus(str, enum.Enum):
    free = "free"
    paid = "paid"
    delinquent = "delinquent"
