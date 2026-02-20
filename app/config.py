import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    server_key: str = Field(
        ..., description="32-byte base64 encoded key for encryption"
    )
    database_url: str = Field(
        "sqlite:///./fedisched.db", description="SQLAlchemy database URL"
    )
    secret_key: str = Field(..., description="Secret key for session cookies")
    environment: str = Field(
        "development", description="Environment: development, production"
    )
    frontend_url: str = Field(
        "http://localhost:5173", description="Frontend URL for CORS"
    )
    backend_url: str = Field(
        "http://localhost:8000", description="Backend URL for CORS"
    )
    log_level: str = Field("INFO", description="Logging level")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
