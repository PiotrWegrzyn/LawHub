"""ASGI entry point: Django for the website, the MCP SDK for /mcp.

Run with: uvicorn config.asgi:application
"""

import os

import django
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from connect.mcp_server import build_asgi_app  # noqa: E402  (needs Django set up)

django_app = get_asgi_application()
mcp_app = build_asgi_app()

MCP_PATHS = ("/mcp", "/.well-known/oauth-protected-resource")


# /healthz serves Cloud Run's startup probe (inside the container); from the
# internet Cloud Run's front end reserves /healthz and answers 404, so external
# checks (deploy smoke test, uptime pings) use /health.
HEALTH_PATHS = {"/healthz", "/health"}


async def healthz(scope, receive, send):
    """Answered before Django: platform probes may use a Host header that isn't
    in ALLOWED_HOSTS, and the check must not need the database."""
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": b"ok"})


async def application(scope, receive, send):
    if scope["type"] == "http" and scope["path"] in HEALTH_PATHS:
        await healthz(scope, receive, send)
    # The MCP app owns the lifespan: it starts the SDK's session manager.
    elif scope["type"] == "lifespan" or scope.get("path", "").startswith(MCP_PATHS):
        await mcp_app(scope, receive, send)
    else:
        await django_app(scope, receive, send)
