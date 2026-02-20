from sqlmodel import SQLModel, create_engine, Session
from app.config import settings

engine = create_engine(settings.database_url, echo=settings.environment == "development")


def create_db_and_tables():
    """Create database tables based on SQLModel models."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Dependency for FastAPI endpoints to get a database session."""
    with Session(engine) as session:
        yield session
