"""OAuth endpoints MCP clients need on top of django-oauth-toolkit.

MCP clients (Claude, Claude Code, ...) discover how to log in from the
`/mcp` resource's metadata, then fetch this server's authorization server
metadata (RFC 8414) and register themselves (RFC 7591 dynamic client
registration) before running the authorization code + PKCE flow that
django-oauth-toolkit implements.
"""

import json
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from oauth2_provider.models import get_application_model

from connect.mcp_server import SCOPE

MAX_REDIRECT_URIS = 5
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def _url(name: str) -> str:
    return f"{settings.LAWHUB_PUBLIC_URL}{reverse(name)}"


@login_not_required
@require_GET
def authorization_server_metadata(request):
    return JsonResponse(
        {
            "issuer": settings.LAWHUB_PUBLIC_URL,
            "authorization_endpoint": _url("oauth2_provider:authorize"),
            "token_endpoint": _url("oauth2_provider:token"),
            "revocation_endpoint": _url("oauth2_provider:revoke-token"),
            "registration_endpoint": _url("connect:register"),
            "scopes_supported": [SCOPE],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        }
    )


def _valid_redirect_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    if parsed.scheme == "https" and parsed.netloc:
        return True
    # Native/CLI clients receive the code on a local port (RFC 8252).
    return parsed.scheme == "http" and parsed.hostname in LOOPBACK_HOSTS


@csrf_exempt
@login_not_required
@require_POST
def register_client(request):
    """RFC 7591 dynamic client registration for public (PKCE) clients."""
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_client_metadata", "error_description": "Body must be JSON."}, status=400)
    redirect_uris = body.get("redirect_uris") or []
    if (
        not isinstance(redirect_uris, list)
        or not 0 < len(redirect_uris) <= MAX_REDIRECT_URIS
        or not all(isinstance(u, str) and _valid_redirect_uri(u) for u in redirect_uris)
    ):
        return JsonResponse(
            {"error": "invalid_redirect_uri", "error_description": "Use https URIs or http loopback URIs."}, status=400
        )

    Application = get_application_model()
    app = Application.objects.create(
        name=str(body.get("client_name") or "MCP client")[:200],
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=" ".join(redirect_uris),
        algorithm="",
        skip_authorization=False,
    )
    return JsonResponse(
        {
            "client_id": app.client_id,
            "client_name": app.name,
            "redirect_uris": redirect_uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPE,
        },
        status=201,
    )
