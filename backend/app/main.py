"""FastAPI application entry point."""

from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title="Tawkeel Backend")

app.include_router(auth_router, prefix="/auth", tags=["auth"])


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return a placeholder health response."""

    return {"status": "ok"}
