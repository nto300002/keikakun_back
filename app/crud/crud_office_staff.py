from app.crud.base import CRUDBase
from app.models.office import OfficeStaff
from typing import Dict, Any

class CRUDOfficeStaff(CRUDBase[OfficeStaff, Dict[str, Any], Dict[str, Any]]):
    pass

office_staff = CRUDOfficeStaff(OfficeStaff)