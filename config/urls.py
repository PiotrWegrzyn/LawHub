from django.contrib import admin
from django.urls import include, path

from connect.oauth import authorization_server_metadata
from connect.urls import oauth_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("tags/", include("tags.urls")),
    path("connect/", include("connect.urls")),
    path("o/", include(oauth_urlpatterns)),
    path(".well-known/oauth-authorization-server", authorization_server_metadata),
    path("", include("laws.urls")),
]
