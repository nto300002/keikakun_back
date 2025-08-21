from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app import crud
from app.db.session import get_db
from app.schemas.debug_message import DebugMessage, DebugMessageCreate

router = APIRouter()

@router.post("/hello", response_model=DebugMessage)
def create_debug_message(
    *, 
    db: Session = Depends(get_db),
    debug_in: DebugMessageCreate
) -> DebugMessage:
    """
    Create new debug message.
    """
    print(f"--- Received message to save: {debug_in.message} ---")
    debug = crud.crud_debug_message.create_debug_message(db=db, obj_in=debug_in)
    print(f"--- Message supposedly saved with ID: {debug.id} ---")
    return debug
