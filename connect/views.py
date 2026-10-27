from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from oauth2_provider.models import get_access_token_model, get_refresh_token_model

from connect.mcp_server import mcp_resource_url


@login_required
def connect_page(request):
    """How to connect your AI, plus the AI apps that currently have access."""
    tokens = (
        get_access_token_model()
        .objects.filter(user=request.user, expires__gt=timezone.now())
        .select_related("application")
        .order_by("-created")
    )
    apps = {}
    for token in tokens:
        apps.setdefault(token.application_id, token.application)
    return render(request, "connect/connect.html", {"mcp_url": mcp_resource_url(), "apps": apps.values()})


@login_required
@require_POST
def revoke_app(request, app_id):
    """Revoke every token one AI app holds for this user."""
    get_refresh_token_model().objects.filter(user=request.user, application_id=app_id).delete()
    get_access_token_model().objects.filter(user=request.user, application_id=app_id).delete()
    return redirect("connect:page")
