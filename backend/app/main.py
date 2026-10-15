"""FastAPI application entry point."""

from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title="Tawkeel Backend")


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return a placeholder health response."""

    return {"status": "ok"}
