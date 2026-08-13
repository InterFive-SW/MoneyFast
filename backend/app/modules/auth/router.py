from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth import schemas, service

router = APIRouter(tags=["auth"])


@router.get("/health")
async def health():
    return {"status": "ok", "module": "auth"}


@router.post("/register", response_model=schemas.UserResponse, status_code=201)
async def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    return service.create_user(payload, db)
