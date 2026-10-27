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


async def application(scope, receive, send):
    # The MCP app owns the lifespan: it starts the SDK's session manager.
    if scope["type"] == "lifespan" or scope.get("path", "").startswith(MCP_PATHS):
        await mcp_app(scope, receive, send)
    else:
        await django_app(scope, receive, send)
