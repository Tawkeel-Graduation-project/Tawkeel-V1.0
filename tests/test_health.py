"""Health route tests."""

from app.main import app


def test_health_returns_ok() -> None:
    route = next(
        route for route in app.routes if getattr(route, "path", None) == "/health"
    )

    assert "GET" in route.methods
    assert route.endpoint() == {"status": "ok"}
