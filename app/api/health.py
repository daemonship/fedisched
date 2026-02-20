from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.database import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(session: Session = Depends(get_session)):
    """Health endpoint verifying database connectivity."""
    # Simple query to ensure DB is reachable
    result = session.exec(select(1)).first()
    if result != 1:
        raise RuntimeError("Database connectivity issue")
    return {"status": "healthy", "database": "connected"}
