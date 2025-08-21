from sqlalchemy.orm import Session
from app.models.debug_message import DebugMessage
from app.schemas.debug_message import DebugMessageCreate

def create_debug_message(db: Session, *, obj_in: DebugMessageCreate) -> DebugMessage:
    print("--- Creating DB object ---")
    db_obj = DebugMessage(
        message=obj_in.message
    )
    db.add(db_obj)
    print("--- db.add() called, attempting to commit... ---")
    db.commit()
    print("--- db.commit() called successfully. ---")
    db.refresh(db_obj)
    print("--- db.refresh() called. ---")
    return db_obj
