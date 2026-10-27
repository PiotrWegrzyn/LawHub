from django.contrib import admin
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.urls import include, path

from connect.oauth import authorization_server_metadata
from connect.urls import oauth_urlpatterns



@login_not_required
def healthz(request):
    """Liveness check for keep-alive pings; deliberately doesn't touch the database
    so pings don't keep the (scale-to-zero) database awake."""
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz", healthz),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("tags/", include("tags.urls")),
    path("connect/", include("connect.urls")),
    path("o/", include(oauth_urlpatterns)),
    path(".well-known/oauth-authorization-server", authorization_server_metadata),
    path("", include("laws.urls")),
]
