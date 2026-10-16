"""FastAPI application entry point."""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.auth.router import router as auth_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title="Tawkeel Backend")


@app.exception_handler(RequestValidationError)
async def auth_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Redact submitted values from authentication validation responses."""
    if not request.url.path.startswith("/auth/"):
        return await request_validation_exception_handler(request, exc)

    detail = [
        {key: error[key] for key in ("loc", "msg", "type") if key in error}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


app.include_router(auth_router, prefix="/auth", tags=["auth"])


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return a placeholder health response."""

    return {"status": "ok"}
