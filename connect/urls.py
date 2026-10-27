from django.contrib.auth.decorators import login_not_required
from django.urls import path
from oauth2_provider import views as oauth_views

from connect import oauth, views

app_name = "connect"

urlpatterns = [
    path("", views.connect_page, name="page"),
    path("apps/<int:app_id>/revoke/", views.revoke_app, name="revoke"),
    path("register/", oauth.register_client, name="register"),
]

# django-oauth-toolkit endpoints, mounted under /o/ in config/urls.py.
# Token and revocation are called by the AI app's server, not a browser
# session, so they must stay reachable when the site requires login.
oauth_urlpatterns = (
    [
        path("authorize/", oauth_views.AuthorizationView.as_view(), name="authorize"),
        path("token/", login_not_required(oauth_views.TokenView.as_view()), name="token"),
        path("revoke_token/", login_not_required(oauth_views.RevokeTokenView.as_view()), name="revoke-token"),
    ],
    "oauth2_provider",
)
