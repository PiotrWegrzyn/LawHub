from django.urls import path

from laws import views

app_name = "laws"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    # source ids contain slashes, e.g. /acts/pl/DU/1997/602/
    path("acts/<str:jurisdiction>/<path:source_id>/", views.act_detail, name="act"),
]
