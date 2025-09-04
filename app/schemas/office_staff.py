from pydantic import BaseModel
import uuid

class StaffOfficeAssociationCreate(BaseModel):
    office_id: uuid.UUID